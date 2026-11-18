# Part of the sms_voipms Odoo module. See LICENSE for details.

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
