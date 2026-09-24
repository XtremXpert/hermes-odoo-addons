# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Réglages de connexion Wazo (URL, token API, tenant)."""

from odoo import fields, models

from ..services.wazo_client import WazoAPIError, WazoClient


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    wazo_url = fields.Char(
        string="URL du serveur Wazo", config_parameter='wazo.url',
        help="ex : https://wazo.diverse-cite.com")
    wazo_api_key = fields.Char(
        string="Token API Wazo", config_parameter='wazo.api_key')
    wazo_tenant_id = fields.Char(
        string="Tenant Wazo (UUID)", config_parameter='wazo.tenant_id',
        help="Laisser vide pour un serveur mono-tenant.")
    wazo_line_context = fields.Char(
        string="Contexte des lignes", config_parameter='wazo.line_context',
        help="Contexte Asterisk utilisé pour les lignes et postes "
             "(défaut : « default »).")
    wazo_voicemail_language = fields.Char(
        string="Langue des messageries vocales",
        config_parameter='wazo.voicemail_language',
        help="ex : fr_CA, en_US (défaut : fr_CA).")
    wazo_connection_ok = fields.Boolean(default=False)

    def action_test_wazo_connection(self):
        """Vérifie la connexion avec un appel en lecture seule."""
        self.ensure_one()
        self.execute()
        client = WazoClient(self.env)
        try:
            client.conf('GET', '/users', params={'limit': 1})
        except WazoAPIError as error:
            self.wazo_connection_ok = False
            raise WazoAPIError(str(error)) from error
        self.wazo_connection_ok = True
