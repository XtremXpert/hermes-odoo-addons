# Part of the sms_voipms Odoo module. See LICENSE for details.

import secrets

from odoo import api
from odoo import fields
from odoo import models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    sms_provider = fields.Selection(
        related="company_id.sms_provider",
        readonly=False,
        required=True,
    )
    sms_voipms_did_id = fields.Many2one(
        related="company_id.sms_voipms_did_id",
        readonly=False,
    )
    sms_voipms_inbound_token = fields.Char(
        string="Jeton de rappel entrant",
        config_parameter="sms_voipms.inbound_token",
        default=lambda self: secrets.token_urlsafe(32),
    )
    sms_voipms_callback_url = fields.Char(
        string="URL de rappel", compute="_compute_sms_voipms_callback_url"
    )

    @api.depends("sms_voipms_inbound_token")
    def _compute_sms_voipms_callback_url(self):
        for settings in self:
            token = settings.sms_voipms_inbound_token or ""
            if token:
                settings.sms_voipms_callback_url = (
                    "%s/sms_voipms/inbound/%s?from={FROM}&to={TO}&message={MESSAGE}"
                    % (settings.company_id.get_base_url(), token)
                )
            else:
                settings.sms_voipms_callback_url = ""

    def action_configure_voipms_callback(self):
        """Generate the token (once) and configure the DID URL callback."""
        self.ensure_one()
        token = self.sms_voipms_inbound_token
        if not token:
            token = secrets.token_urlsafe(32)
            self.sms_voipms_inbound_token = token
        self.env["ir.config_parameter"].sudo().set_str("sms_voipms.inbound_token", token)
        self.company_id._configure_voipms_callback()
        return True
