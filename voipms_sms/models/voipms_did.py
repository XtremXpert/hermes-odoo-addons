# Part of the voipms_sms Odoo module. See LICENSE for details.
"""DID : numéro d'émetteur de SMS (appartenant au compte VoIP.ms)."""

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.voipms_client import VoIPMSClient
from ..services.sms_segmentation import normalize_nanp


class VoIPMSDid(models.Model):
    _name = 'voipms.did'
    _description = 'VoIP.ms : DID (numéro d\'émetteur)'
    _order = 'number'

    number = fields.Char(string='Numéro', required=True)
    label = fields.Char(string='Étiquette')
    sms_available = fields.Boolean(string='SMS disponible')
    sms_enabled = fields.Integer(string='SMS activé', default=0,
                                 help='0 = désactivé, 1 = activé')
    synced = fields.Boolean(string='Synchronisé avec VoIP.ms')
    active = fields.Boolean(string='Actif', default=True)

    _number_uniq = models.Constraint(
        'unique(number)', 'Ce numéro existe déjà.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            try:
                number = normalize_nanp(vals.get('number') or '')
            except ValueError as error:
                raise UserError(str(error)) from error
            if self.search([('number', '=', number)], limit=1):
                raise UserError(
                    'Le numéro %s existe déjà.' % number)
            vals['number'] = number
        return super().create(vals_list)

    def action_sync_from_provider(self):
        """Aligne l'état local sur le serveur (getDIDsInfo)."""
        self.ensure_one()
        client = VoIPMSClient(self.env)
        response = client._request('getDIDsInfo')
        entries = response.get('did') or []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get('did'):
                continue
            try:
                number = normalize_nanp(entry['did'])
            except ValueError:
                continue
            did = self.search([('number', '=', number)], limit=1)
            values = {
                'sms_available': bool(entry.get('sms_available')),
                'sms_enabled': int(str(entry.get('sms_enabled') or '0')),
                'synced': True,
            }
            if did:
                did.write(values)
            else:
                self.create(dict(values, number=number))
        return True