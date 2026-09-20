# Part of the mailcow_admin Odoo module. See LICENSE for details.
from odoo import fields, models

from ..services.mailcow_client import MailcowClient


class MailcowDomain(models.Model):
    _name = 'mailcow.domain'
    _description = 'Mailcow: domaine'
    _order = 'name'

    name = fields.Char(string='Domaine', required=True, index=True)
    description = fields.Char(string='Description')
    dkim = fields.Boolean(string='Clé DKIM', default=True)
    quota_mb = fields.Integer(string='Quota (Mo)', default=0, help='0 = illimité')
    active = fields.Boolean(string='Actif', default=True)
    synced = fields.Boolean(string='Synchronisé avec Mailcow')
    mailcow_id = fields.Char(string='ID Mailcow', readonly=True)
    mailboxes = fields.One2many('mailcow.mailbox', 'domain_id', string='Boîtes mail')
    aliases = fields.One2many('mailcow.alias', 'domain_id', string='Alias')

    _name_uniq = models.Constraint(
        'unique(name)', 'Ce domaine existe déjà.')

    # --- Actions Mailcow --------------------------------------------------

    def _payload(self):
        self.ensure_one()
        return {
            'domain': self.name,
            'description': self.description or '',
            'dkim': self.dkim,
            'quota': self.quota_mb * 1024,  # Mailcow attend un quota en Ko
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
            client._request('POST', '/edit/domain', domain._payload())
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
        """Aligne l'état local sur le serveur (GET /get/domain/111)."""
        self.ensure_one()
        client = MailcowClient(self.env)
        response = client._request('GET', '/get/domain/111', None)
        entries = response.get('data') if isinstance(response, dict) else response
        remote_ids = set()
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get('domain'):
                continue
            remote_ids.add(entry['domain'])
            domain = self.env['mailcow.domain'].search([('name', '=', entry['domain'])], limit=1)
            values = {
                'description': entry.get('description') or '',
                'dkim': bool(entry.get('dkim')),
                'quota_mb': int(entry.get('quota') or 0) // 1024,
                'active': entry.get('active') in (1, '1', True),
                'synced': True,
            }
            if entry.get('id') is not None:
                values['mailcow_id'] = str(entry['id'])
            if domain:
                domain.write(values)
            else:
                self.env['mailcow.domain'].create(
                    dict(values, name=entry['domain']))
        # Les domaines locaux absents du serveur ne sont plus « synchronisés ».
        self.env['mailcow.domain'].search(
            [('name', 'not in', list(remote_ids)), ('active', '=', True)]
        ).write({'synced': False})
        return True
