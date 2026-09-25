# Part of the mailcow_admin Odoo module. See LICENSE for details.
from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.mailcow_client import (
    MailcowClient,
    en_nombre,
    refuser_la_disparition_totale,
)


class MailcowDomain(models.Model):
    _name = 'mailcow.domain'
    _description = 'Mailcow: domaine'
    _order = 'name'

    name = fields.Char(string='Domaine', required=True, index=True)
    description = fields.Char(string='Description')
    quota_mb = fields.Integer(string='Quota (Mo)', default=0, help='0 = illimité')
    dkim_record = fields.Text(
        string='Enregistrement DKIM (DNS)',
        readonly=True,
        help="La ligne à publier dans le DNS du domaine. Jamais la clé privée.",
    )
    active = fields.Boolean(string='Actif', default=True)
    synced = fields.Boolean(string='Synchronisé avec Mailcow')
    mailboxes = fields.One2many('mailcow.mailbox', 'domain_id', string='Boîtes mail')
    aliases = fields.One2many('mailcow.alias', 'domain_id', string='Alias')

    _name_uniq = models.Constraint(
        'unique(name)', 'Ce domaine existe déjà.')

    # --- Actions Mailcow --------------------------------------------------

    def _attr_payload(self):
        """Les attributs modifiables d'un domaine : le « attr » d'une édition.

        Mailcow attend {"items": [domaine], "attr": {...}} et ignore un corps
        plat en répondant « success ». Le nom est l'identité, pas un attribut.
        Les quotas sont en OCTETS ; un quota local à 0 vaut « illimité », on
        n'envoie donc rien plutôt que d'effacer la politique du serveur.
        """
        self.ensure_one()
        attr = {
            'description': self.description or '',
            'active': '1' if self.active else '0',
        }
        if self.quota_mb > 0:
            octets = self.quota_mb * 1024 * 1024
            attr['def_quota_for_mbox'] = octets
            attr['max_quota_for_domain'] = octets
        return attr

    def _payload(self):
        """La charge de création : le nom, plus les attributs modifiables."""
        self.ensure_one()
        return dict(self._attr_payload(), domain=self.name)

    def action_fetch_dkim(self):
        """Relit la clé DKIM PUBLIQUE du domaine, à publier dans le DNS.

        Mailcow renvoie aussi la clé privée dans la même réponse : elle n'est
        jamais lue ici, et donc jamais rangée dans Odoo.
        """
        self.ensure_one()
        client = MailcowClient(self.env)
        reponse = client._request('GET', '/get/dkim/%s' % self.name, None)
        if isinstance(reponse, list) and reponse:
            reponse = reponse[0]
        if not isinstance(reponse, dict) or not reponse.get('dkim_txt'):
            raise UserError(
                "Le serveur n'a pas renvoyé de clé DKIM publique pour « %s »."
                % self.name
            )
        selecteur = reponse.get('dkim_selector') or 'dkim'
        valeur = reponse['dkim_txt']
        if isinstance(valeur, list):
            valeur = ''.join(valeur)
        self.dkim_record = '%s._domainkey.%s   TXT   "%s"' % (
            selecteur, self.name, valeur)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': 'Mailcow',
                'sticky': False,
                'message': "L'enregistrement DKIM de %s est prêt." % self.name,
            },
        }

    def action_create_on_mailcow(self):
        """Crée le domaine sur Mailcow (ou le met à jour s'il existe déjà)."""
        for domain in self:
            client = MailcowClient(self.env)
            client._request('POST', '/add/domain', domain._payload())
            domain.write({'synced': True})

    def action_update_on_mailcow(self):
        """Réécrit l'état local sur Mailcow."""
        for domain in self:
            client = MailcowClient(self.env)
            client._request('POST', '/edit/domain', {
                'items': [domain.name],
                'attr': domain._attr_payload(),
            })
            domain.write({'synced': True})

    def action_delete_on_mailcow(self):
        """Supprime le domaine sur Mailcow, puis l'archive localement."""
        for domain in self:
            client = MailcowClient(self.env)
            client._request('POST', '/delete/domain', {'domain': domain.name})
            domain.mailboxes.write({'synced': False})
            domain.aliases.write({'synced': False})
            domain.write({'synced': False, 'active': False})

    def action_sync_from_mailcow(self):
        """Synchronise depuis cette fiche (voir action_sync_all_from_mailcow)."""
        self.ensure_one()
        return self.env['mailcow.domain'].action_sync_all_from_mailcow()

    @api.model
    def action_sync_all_from_mailcow(self):
        """Aligne tout l'état local sur le serveur (GET /get/domain/all).

        S'appelle sans aucune fiche locale : c'est ainsi qu'on amorce une base
        vide, depuis l'en-tête d'une vue de liste ou le menu « Tout synchroniser ».
        """
        client = MailcowClient(self.env)
        response = client._request('GET', '/get/domain/all', None)
        entries = response.get('data') if isinstance(response, dict) else response
        refuser_la_disparition_totale(
            self.env, entries, 'mailcow.domain', 'domaine')
        remote_ids = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            # Mailcow nomme le domaine « domain_name » ; « domain » n'existe pas,
            # et s'y fier fait ignorer chaque entrée en silence.
            nom = entry.get('domain_name') or entry.get('domain')
            if not nom:
                continue
            remote_ids.add(nom)
            domain = self.env['mailcow.domain'].search([('name', '=', nom)], limit=1)
            values = {
                'description': entry.get('description') or '',
                # Mailcow renvoie les quotas en octets.
                # Le quota peut arriver en texte : int() ferait lever la
                # synchronisation sur une valeur parfaitement valide.
                'quota_mb': int(en_nombre(entry.get('def_quota_for_mbox'))) // (1024 * 1024),
                'active': entry.get('active') in (1, '1', True),
                'synced': True,
            }
            if domain:
                domain.write(values)
            else:
                self.env['mailcow.domain'].create(
                    dict(values, name=nom))
        # Les domaines locaux absents du serveur ne sont plus « synchronisés ».
        self.env['mailcow.domain'].search(
            [('name', 'not in', list(remote_ids)), ('active', '=', True)]
        ).write({'synced': False})
        return True
