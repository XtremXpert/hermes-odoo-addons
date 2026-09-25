# Part of the voipms_sms Odoo module. See LICENSE for details.
"""Réglages de connexion VoIP.ms (utilisateur + token)."""

from odoo.exceptions import UserError

from odoo import fields
from odoo import models

from ..services.voipms_client import VoIPMSAPIError
from ..services.voipms_client import VoIPMSClient


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    voipms_api_username = fields.Char(
        string='Utilisateur API', config_parameter='voipms.api_username')
    voipms_api_token = fields.Char(
        string='Token API', config_parameter='voipms.api_token')
    voipms_connection_ok = fields.Boolean(default=False)

    def action_test_voipms_connection(self):
        """Vérifie la connexion avec un appel en lecture seule (getBalance)."""
        self.ensure_one()
        client = VoIPMSClient(self.env)
        try:
            client._request('getBalance')
            self.voipms_connection_ok = True
        except VoIPMSAPIError as error:
            self.voipms_connection_ok = False
            raise UserError(str(error)) from error
