# Part of the sms_voipms Odoo module. See LICENSE for details.
"""Company-level SMS provider choice and sender DID."""

from odoo import api
from odoo import fields
from odoo import models
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSClient
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

from ..tools.sms_api import SmsApiVoIPMS


class ResCompany(models.Model):
    _inherit = "res.company"

    sms_provider = fields.Selection(
        selection=[
            ("iap", "Envoyer via Odoo (IAP)"),
            ("voipms", "Envoyer via VoIP.ms"),
        ],
        string="Fournisseur SMS",
        default="iap",
        required=True,
    )
    sms_voipms_did_id = fields.Many2one(
        "voipms.did",
        string="DID expéditeur",
        ondelete="restrict",
        domain=[("sms_enabled", "=", 1), ("active", "=", True)],
    )

    def _get_sms_api_class(self):
        self.ensure_one()
        if self.sms_provider == "voipms":
            return SmsApiVoIPMS
        return super()._get_sms_api_class()

    def _assert_sms_voipms_ready(self):
        """Refuse a VoIP.ms send before any HTTP call.

        Called by ``sms.sms.send`` (interactive path) and by
        ``SmsApiVoIPMS._send_sms_batch`` (cron path), so a misconfigured
        company never reaches the API.
        """
        self.ensure_one()
        if self.sms_provider != "voipms":
            return
        did = self.sms_voipms_did_id
        if not did:
            raise UserError(
                self.env._("Choisissez le DID expéditeur VoIP.ms dans les réglages SMS.")
            )
        if not did.active or did.sms_enabled != 1:
            raise UserError(self.env._("Le DID %s n'a pas le SMS activé chez VoIP.ms.", did.number))

    @api.constrains("sms_provider", "sms_voipms_did_id")
    def _check_sms_voipms_config(self):
        for company in self:
            if company.sms_provider == "voipms" and not company.sms_voipms_did_id:
                raise ValidationError(self.env._("Le fournisseur VoIP.ms exige un DID expéditeur."))

    def _configure_voipms_callback(self):
        """Enable SMS and set the inbound URL callback on the sender DID."""
        self.ensure_one()
        self._assert_sms_voipms_ready()
        token = self.env["ir.config_parameter"].sudo().get_str("sms_voipms.inbound_token")
        if not token:
            raise UserError(self.env._("Générez d'abord le jeton de rappel dans les réglages SMS."))
        number = self.sms_voipms_did_id.number
        did = number[1:] if len(number) == 11 and number.startswith("1") else number
        callback = "%s/sms_voipms/inbound/%s?from={FROM}&to={TO}&message={MESSAGE}" % (
            self.get_base_url(),
            token,
        )
        VoIPMSClient(self.env).set_sms(
            did,
            enable=1,
            url_callback=callback,
            url_callback_enabled=1,
            url_callback_retry=1,
        )
        return True
