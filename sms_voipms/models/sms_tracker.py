# Part of the sms_voipms Odoo module. See LICENSE for details.

from odoo import fields
from odoo import models


class SmsTracker(models.Model):
    _inherit = "sms.tracker"

    sms_voipms_message_ids = fields.Char(string="Identifiants VoIP.ms", readonly=True)
