# Part of the mailcow_admin Odoo module. See LICENSE for details.
from odoo import fields, models
from odoo.exceptions import UserError

from ..services.mailcow_client import MailcowClient


class MailcowAlias(models.Model):
    _name = 'mailcow.alias'
    _description = 'Mailcow: alias'
    _order = 'domain_id, alias_name'

    alias_name = fields.Char(string="Nom d'alias", required=True)
    domain_id = fields.Many2one(
        'mailcow.domain', string='Domaine', required=True,
        ondelete='cascade', index=True,
    )
    address_ids = fields.Many2many('mailcow.email_address', string='Adresses de destination')
    active = fields.Boolean(string='Actif', default=True)
    description = fields.Char(string='Description')
    synced = fields.Boolean(string='Synchronisé avec Mailcow')
    mailcow_id = fields.Char(string='ID Mailcow', readonly=True)

    _alias_domain_uniq = models.Constraint(
        'unique(alias_name, domain_id)',
        'Cet alias existe déjà sur ce domaine.')

    # --- Actions Mailcow --------------------------------------------------

    def _payload(self):
        self.ensure_one()
        return {
            'alias_name': self.alias_name,
            'domain': self.domain_id.name,
            'address': self.address_ids.mapped('address'),
            'active': '1' if self.active else '0',
            'description': self.description or '',
        }

    def _ensure_addresses(self):
        self.ensure_one()
        if not self.address_ids:
            raise UserError(
                "Renseignez au moins une adresse de destination pour l'alias « %s » "
                "avant de le créer sur Mailcow." % self.alias_name
            )

    def action_create_on_mailcow(self):
        """Crée l'alias sur Mailcow."""
        for alias in self:
            alias._ensure_addresses()
            client = MailcowClient(self.env)
            client._request('POST', '/add/alias', alias._payload())
            alias.write({'synced': True})

    def action_update_on_mailcow(self):
        """Réécrit l'état local sur Mailcow."""
        for alias in self:
            alias._ensure_addresses()
            client = MailcowClient(self.env)
            client._request('POST', '/edit/alias', alias._payload())
            alias.write({'synced': True})

    def action_delete_on_mailcow(self):
        """Supprime l'alias sur Mailcow, puis l'archive localement."""
        for alias in self:
            client = MailcowClient(self.env)
            client._request('POST', '/delete/alias', {
                'alias_name': alias.alias_name,
                'domain': alias.domain_id.name,
            })
            alias.write({'synced': False, 'active': False})

    def _address_records(self, addresses):
        """Renvoie (en créant au besoin) les enregistrements d'adresse."""
        records = self.env['mailcow.email_address']
        for address in addresses:
            record = self.env['mailcow.email_address'].search(
                [('address', '=', address)], limit=1)
            if not record:
                record = self.env['mailcow.email_address'].create(
                    {'address': address})
            records |= record
        return records

    def action_sync_from_mailcow(self):
        """Aligne l'état local sur le serveur (GET /get/alias/111)."""
        self.ensure_one()
        client = MailcowClient(self.env)
        response = client._request('GET', '/get/alias/111', None)
        entries = response.get('data') if isinstance(response, dict) else response
        remote_keys = set()
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get('alias_name') or not entry.get('domain'):
                continue
            domain = self.env['mailcow.domain'].search(
                [('name', '=', entry['domain'])], limit=1)
            if not domain:  # domaine vu côté serveur, créé à la volée
                domain = self.env['mailcow.domain'].create({'name': entry['domain']})
            remote_keys.add((entry['alias_name'], domain.id))
            alias = self.env['mailcow.alias'].search(
                [('alias_name', '=', entry['alias_name']),
                 ('domain_id', '=', domain.id)],
                limit=1,
            )
            values = {
                'description': entry.get('description') or '',
                'active': entry.get('active') in (1, '1', True),
                'synced': True,
                'address_ids': [(6, 0, self._address_records(
                    entry.get('address') or []
                ).ids)],
            }
            if entry.get('id') is not None:
                values['mailcow_id'] = str(entry['id'])
            if alias:
                alias.write(values)
            else:
                self.env['mailcow.alias'].create(
                    dict(values, alias_name=entry['alias_name'], domain_id=domain.id))
        # Les alias locaux absents du serveur ne sont plus « synchronisés ».
        self.env['mailcow.alias'].search([('active', '=', True)]).filtered(
            lambda a: (a.alias_name, a.domain_id.id) not in remote_keys
        ).write({'synced': False})
        return True
