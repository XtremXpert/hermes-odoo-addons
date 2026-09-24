# Part of the mailcow_admin Odoo module. See LICENSE for details.
from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.mailcow_client import MailcowClient


class MailcowMailbox(models.Model):
    _name = 'mailcow.mailbox'
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
    mailcow_id = fields.Char(string='ID Mailcow', readonly=True)
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

    def _base_payload(self, with_password=False):
        self.ensure_one()
        payload = {
            'local_part': self.local_part,
            'domain': self.domain_id.name,
            'quota': self.quota_mb,  # Mailcow compte les quotas en mébioctets
            'active': '1' if self.active else '0',
            'name': self.name or '',
            'description': self.description or '',
            'tls_enforce_in': '1' if self.tls_enforce_in else '0',
            'tls_enforce_out': '1' if self.tls_enforce_out else '0',
        }
        if with_password:
            password = self.password
            payload['password'] = password
            payload['password2'] = password
        return payload

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
            mailbox.write({'synced': True})
            mailbox.password = False  # le mot de passe ne doit pas rester dans Odoo

    def action_update_on_mailcow(self):
        """Réécrit l'état local sur Mailcow (jamais le mot de passe)."""
        for mailbox in self:
            client = MailcowClient(self.env)
            client._request('POST', '/edit/mailbox', mailbox._base_payload())
            mailbox.write({'synced': True})

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
                'quota_mb': int(entry.get('quota') or 0) // (1024 * 1024),
                'active': entry.get('active') in (1, '1', True),
                'synced': True,
            }
            if entry.get('id') is not None:
                values['mailcow_id'] = str(entry['id'])
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
