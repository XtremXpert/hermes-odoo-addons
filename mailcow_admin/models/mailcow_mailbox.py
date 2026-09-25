# Part of the mailcow_admin Odoo module. See LICENSE for details.
from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.mailcow_client import (
    MailcowClient,
    en_date as _en_date,
    en_nombre as _en_nombre,
    refuser_la_disparition_totale,
)


class MailcowMailbox(models.Model):
    _name = 'mailcow.mailbox'
    _inherit = ['mailcow.sync.mixin']
    _description = 'Mailcow: boîte mail'
    _order = 'domain_id, local_part'

    local_part = fields.Char(string="Nom d'utilisateur", required=True)
    domain_id = fields.Many2one(
        'mailcow.domain', string='Domaine', required=True,
        ondelete='cascade', index=True,
    )
    name = fields.Char(string='Nom complet')
    description = fields.Char(string='Description')
    quota_mb = fields.Integer(string='Quota (Mo)', default=0, help='0 = illimité')
    active = fields.Boolean(string='Actif', default=True)
    synced = fields.Boolean(string='Synchronisé avec Mailcow')
    # Ce que Mailcow sait de chaque boîte et que le module ignorait.
    # En décimal : une boîte de 87 Ko ne doit pas s'afficher à 0.
    quota_used_mb = fields.Float(
        string='Utilisé (Mo)', readonly=True, digits=(12, 2))
    percent_in_use = fields.Float(
        string='Occupation (%)', readonly=True, digits=(5, 1))
    messages = fields.Integer(string='Messages', readonly=True)
    last_imap_login = fields.Datetime(string='Dernière connexion IMAP', readonly=True)
    last_smtp_login = fields.Datetime(string='Dernière connexion SMTP', readonly=True)
    last_pop3_login = fields.Datetime(string='Dernière connexion POP3', readonly=True)
    password = fields.Char(
        string='Mot de passe',
        help="Utilisé à la création et à la réinitialisation. Jamais stocké dans Odoo.",
    )

    _local_domain_uniq = models.Constraint(
        'unique(local_part, domain_id)',
        'Cette boîte mail existe déjà sur ce domaine.')

    email = fields.Char(
        string='Adresse', compute='_compute_email', store=True,
        readonly=True,
    )
    tls_enforce_in = fields.Boolean(string='TLS entrant obligatoire', default=True)
    tls_enforce_out = fields.Boolean(string='TLS sortant obligatoire', default=True)

    @api.depends('local_part', 'domain_id', 'domain_id.name')
    def _compute_email(self):
        for rec in self:
            if rec.local_part and rec.domain_id:
                rec.email = f"{rec.local_part}@{rec.domain_id.name}"
            else:
                rec.email = None

    # --- Actions Mailcow --------------------------------------------------

    def _attr_payload(self, with_password=False):
        """Les attributs modifiables d'une boîte : le « attr » d'une édition.

        L'adresse est l'identité (elle va dans « items »), pas un attribut.
        """
        self.ensure_one()
        attr = {
            'quota': self.quota_mb,  # Mailcow compte les quotas en mébioctets
            'active': '1' if self.active else '0',
            'name': self.name or '',
            'description': self.description or '',
            'tls_enforce_in': '1' if self.tls_enforce_in else '0',
            'tls_enforce_out': '1' if self.tls_enforce_out else '0',
        }
        if with_password:
            attr['password'] = self.password
            attr['password2'] = self.password
        return attr

    def _base_payload(self, with_password=False):
        """La charge de création : l'identité, plus les attributs."""
        self.ensure_one()
        return dict(
            self._attr_payload(with_password),
            local_part=self.local_part,
            domain=self.domain_id.name,
        )

    def action_create_on_mailcow(self):
        """Crée la boîte mail sur Mailcow (un mot de passe est requis)."""
        for mailbox in self:
            if not mailbox.password:
                raise UserError(
                    "Saisissez un mot de passe pour « %s » avant de créer "
                    "la boîte mail sur Mailcow." % mailbox.email
                )
            client = MailcowClient(self.env)
            client._request('POST', '/add/mailbox', mailbox._base_payload(with_password=True))
            mailbox.write({'last_synced_on': fields.Datetime.now(), 'synced': True})
            mailbox.password = False  # le mot de passe ne doit pas rester dans Odoo

    def action_make_catch_all(self):
        """Fait de cette boîte le fourre-tout de son domaine.

        Un fourre-tout est un alias dont l'adresse est « @domaine » : s'il en
        existe déjà un, il est réorienté, sinon il est créé.
        """
        self.ensure_one()
        if not self.synced:
            raise UserError(
                "Créez d'abord la boîte « %s » sur Mailcow : un fourre-tout doit "
                "pointer vers une adresse qui existe." % self.email
            )
        domaine = self.domain_id
        adresse = self.env['mailcow.email_address'].search(
            [('address', '=', self.email)], limit=1)
        if not adresse:
            adresse = self.env['mailcow.email_address'].create(
                {'address': self.email})
        fourre_tout = self.env['mailcow.alias'].search(
            [('domain_id', '=', domaine.id), ('is_catch_all', '=', True)],
            limit=1,
        )
        if fourre_tout:
            fourre_tout.write({'address_ids': [(6, 0, [adresse.id])]})
            if fourre_tout.synced:
                fourre_tout.action_update_on_mailcow()
            else:
                fourre_tout.action_create_on_mailcow()
        else:
            fourre_tout = self.env['mailcow.alias'].create({
                'domain_id': domaine.id,
                'is_catch_all': True,
                'address_ids': [(6, 0, [adresse.id])],
                'description': 'Fourre-tout, depuis la boîte %s' % self.email,
            })
            fourre_tout.action_create_on_mailcow()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': 'Mailcow',
                'sticky': False,
                'message': 'Le fourre-tout de %s pointe vers %s.'
                           % (domaine.name, self.email),
            },
        }

    def action_update_on_mailcow(self):
        """Réécrit l'état local sur Mailcow (jamais le mot de passe)."""
        for mailbox in self:
            client = MailcowClient(self.env)
            client._request('POST', '/edit/mailbox', {
                'items': [mailbox.email],
                'attr': mailbox._attr_payload(),
            })
            mailbox.write({'last_synced_on': fields.Datetime.now(), 'synced': True})

    def action_reset_password(self):
        """Ouvre le wizard de réinitialisation du mot de passe."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Nouveau mot de passe',
            'res_model': 'mailcow.mailbox.password',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_mailbox_id': self.id},
        }

    def action_delete_on_mailcow(self):
        """Supprime la boîte mail sur Mailcow, puis l'archive localement."""
        for mailbox in self:
            client = MailcowClient(self.env)
            # Mailcow exige l'adresse complète : « local_part » + « domain »
            # lui vaut un access_denied, même avec une clé pleinement habilitée.
            client._request('POST', '/delete/mailbox', {
                'mail_user': mailbox.email,
            })
            mailbox.write({'synced': False, 'active': False})

    def action_sync_from_mailcow(self):
        """Synchronise depuis cette fiche (voir action_sync_all_from_mailcow)."""
        self.ensure_one()
        return self.env['mailcow.mailbox'].action_sync_all_from_mailcow()

    @api.model
    def action_sync_all_from_mailcow(self):
        """Aligne tout l'état local sur le serveur (GET /get/mailbox/all).

        S'appelle sans aucune fiche locale : c'est ainsi qu'on amorce une base
        vide, depuis l'en-tête d'une vue de liste ou le menu « Tout synchroniser ».
        """
        client = MailcowClient(self.env)
        response = client._request('GET', '/get/mailbox/all', None)
        entries = response.get('data') if isinstance(response, dict) else response
        refuser_la_disparition_totale(
            self.env, entries, 'mailcow.mailbox', 'boîte mail')
        remote_keys = set()
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get('domain'):
                continue
            # Mailcow renvoie « local_part » et « username » ; « mail_user »
            # n'existe pas, et s'y fier fait ignorer chaque entrée en silence.
            local_part = entry.get('local_part')
            if not local_part:
                identifiant = entry.get('mail_user') or entry.get('username') or ''
                local_part = identifiant.split('@')[0]
            if not local_part:
                continue
            domain_name = entry['domain']
            remote_keys.add((local_part, domain_name))
            domain = self.env['mailcow.domain'].search([('name', '=', domain_name)], limit=1)
            if not domain:  # domaine vu côté serveur, créé à la volée
                domain = self.env['mailcow.domain'].create({'name': domain_name})
            mailbox = self.env['mailcow.mailbox'].search(
                [('local_part', '=', local_part),
                 ('domain_id', '=', domain.id)],
                limit=1,
            )
            values = {
                'name': entry.get('name') or '',
                'description': entry.get('description') or '',
                # Mailcow renvoie les quotas en octets (écriture en Mo).
                # Les nombres peuvent arriver en texte : on convertit sans
                # supposer, sinon un quota textuel ferait lever la synchro.
                'quota_mb': int(_en_nombre(entry.get('quota'))) // (1024 * 1024),
                'active': entry.get('active') in (1, '1', True),
                'synced': True,
                'last_synced_on': fields.Datetime.now(),
                # L'usage réel, lu à chaque synchronisation.
                'quota_used_mb': _en_nombre(entry.get('quota_used')) / (1024 * 1024),
                'percent_in_use': _en_nombre(entry.get('percent_in_use')),
                'messages': int(_en_nombre(entry.get('messages'))),
                'last_imap_login': _en_date(entry.get('last_imap_login')),
                'last_smtp_login': _en_date(entry.get('last_smtp_login')),
                'last_pop3_login': _en_date(entry.get('last_pop3_login')),
            }
            if mailbox:
                mailbox.write(values)
            else:
                self.env['mailcow.mailbox'].create(
                    dict(values, local_part=local_part, domain_id=domain.id))
        # Les boîtes locales absentes du serveur ne sont plus « synchronisées ».
        self.env['mailcow.mailbox'].search([('active', '=', True)]).filtered(
            lambda m: (m.local_part, m.domain_id.name) not in remote_keys
        ).write({'synced': False})
        return True
