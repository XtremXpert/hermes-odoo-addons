# Part of the mailcow_admin Odoo module. See LICENSE for details.
from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError

from ..services.mailcow_client import MailcowClient
from ..services.mailcow_client import en_nombre
from ..services.mailcow_client import refuser_la_disparition_totale


class MailcowDomain(models.Model):
    _name = 'mailcow.domain'
    _inherit = ['mailcow.sync.mixin']
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

        Les quotas s'écrivent en MIO sous les noms « defquota », « maxquota »
        et « quota » — les mêmes pour /add/domain et pour /edit/domain, comme
        le montre l'exemple de l'API (« defquota: 3072 », « maxquota: 10240 »,
        qui sont aussi les valeurs par défaut du serveur). « def_quota_for_mbox »
        et « max_quota_for_domain » sont les noms de la RELECTURE : mesuré sur
        le serveur, /edit/domain les recopie dans son journal, répond
        « success », et n'applique rien.

        Un quota local à 0 vaut « illimité » : on n'envoie rien plutôt que
        d'écraser la politique de quotas du serveur.
        """
        self.ensure_one()
        attr = {
            'description': self.description or '',
            'active': '1' if self.active else '0',
        }
        if self.quota_mb > 0:
            attr['defquota'] = self.quota_mb
            attr['maxquota'] = self.quota_mb
            attr['quota'] = self.quota_mb
        return attr

    def _payload(self):
        """La charge de création : le nom, plus les attributs modifiables.

        Les deux routes d'écriture, /add/domain et /edit/domain, partagent le
        vocabulaire décrit dans _attr_payload : les quotas s'y écrivent en MIO.
        """
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
            domain.write({'last_synced_on': fields.Datetime.now(), 'synced': True})
            domain._journaliser('Domaine %s créé sur Mailcow.' % domain.name)

    def action_update_on_mailcow(self):
        """Réécrit l'état local sur Mailcow."""
        for domain in self:
            client = MailcowClient(self.env)
            client._request('POST', '/edit/domain', {
                'items': [domain.name],
                'attr': domain._attr_payload(),
            })
            domain.write({'last_synced_on': fields.Datetime.now(), 'synced': True})
            domain._journaliser('Mise à jour poussée vers Mailcow.')

    def action_delete_on_mailcow(self):
        """Supprime le domaine sur Mailcow, puis l'archive localement."""
        for domain in self:
            client = MailcowClient(self.env)
            client._request('POST', '/delete/domain', {'domain': domain.name})
            domain.mailboxes.write({'synced': False})
            domain.aliases.write({'synced': False})
            domain.write({'synced': False, 'active': False})
            domain._journaliser('Supprimé de Mailcow, et archivé ici.')

    def action_sync_from_mailcow(self):
        """Synchronise depuis cette fiche (voir action_sync_all_from_mailcow)."""
        self.ensure_one()
        return self.env['mailcow.domain'].action_sync_all_from_mailcow()

    @api.model
    def action_sync_all_from_mailcow(self):
        """Aligner tout l'état local sur le serveur (bouton et menu)."""
        return self._sync_all_from_mailcow()

    @api.model
    def _sync_all_from_mailcow(self, dry_run=False):
        """Décrire, ou appliquer, l'état du serveur sur les fiches locales.

        S'appelle sans aucune fiche locale : c'est ainsi qu'on amorce une base
        vide, depuis l'en-tête d'une vue de liste ou le menu « Tout synchroniser ».
        """
        plan = []
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
            # Les fiches archivees comptent : une suppression archive la fiche
            # locale, et le domaine qui reapparait ensuite doit etre ravive, pas
            # recree — la contrainte d'unicite sur le nom ferait echouer toute
            # la synchronisation.
            domain = self.env['mailcow.domain'].with_context(
                active_test=False).search([('name', '=', nom)], limit=1)
            values = {
                'description': entry.get('description') or '',
                # Mailcow renvoie les quotas en octets.
                # Le quota peut arriver en texte : int() ferait lever la
                # synchronisation sur une valeur parfaitement valide.
                'quota_mb': int(en_nombre(entry.get('def_quota_for_mbox'))) // (1024 * 1024),
                'active': entry.get('active') in (1, '1', True),
                'synced': True,
                'last_synced_on': fields.Datetime.now(),
            }
            if domain:
                self._poser(domain, values, plan, dry_run)
            else:
                self._creer('mailcow.domain', dict(values, name=nom),
                            plan, dry_run, nom)
        # Les domaines locaux absents du serveur ne sont plus « synchronisés ».
        disparues = self.env['mailcow.domain'].search(
            [('name', 'not in', list(remote_ids)), ('active', '=', True)])
        if dry_run:
            for fiche in disparues:
                plan.append('%s « %s » : disparue du serveur'
                            % (self._description, fiche._designation()))
        else:
            disparues.write({'synced': False})
        return plan
