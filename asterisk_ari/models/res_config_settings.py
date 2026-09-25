# Part of the asterisk_ari Odoo module. See LICENSE for details.
"""Réglages de connexion Asterisk ARI (FreePBX)."""

from odoo.exceptions import UserError

from odoo import fields
from odoo import models

from ..services.ari_client import ARI
from ..services.ari_client import ARIConfigError
from ..services.ari_client import ARIError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    asterisk_base_url = fields.Char(
        string="URL ARI (ex. http://pbx:8088/ari)",
        config_parameter='asterisk_ari.base_url')
    asterisk_app_name = fields.Char(
        string="Application ARI",
        config_parameter='asterisk_ari.app_name')
    asterisk_api_token = fields.Char(
        string="Jeton ARI", password=True,
        config_parameter='asterisk_ari.api_token')
    asterisk_connection_ok = fields.Boolean(default=False)

    def action_test_ari_connection(self):
        """Vérifie la connexion avec un appel en lecture seule (GET /apps)."""
        self.ensure_one()
        client = ARI(self.env)
        try:
            client.list_apps()
            self.asterisk_connection_ok = True
        except (ARIError, ARIConfigError) as error:
            self.asterisk_connection_ok = False
            raise UserError(str(error)) from error
