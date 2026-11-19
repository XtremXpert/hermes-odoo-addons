# Part of the sms_voipms Odoo module. See LICENSE for details.

from unittest.mock import patch

from odoo.addons.voipms_sms.services.voipms_client import VoIPMSClient
from odoo.exceptions import UserError
from odoo.tests import TransactionCase

from .common import SmsVoipmsCommon


class TestCallbackConfig(SmsVoipmsCommon, TransactionCase):
    def test_configure_sends_set_sms_on_sender_did(self):
        """The configure button calls setSMS with the callback URL."""
        self.env["ir.config_parameter"].sudo().set_str("sms_voipms.inbound_token", "tok")
        with patch.object(VoIPMSClient, "_request", return_value={"status": "success"}) as request:
            self.company._configure_voipms_callback()
        request.assert_called_once()
        method, params = request.call_args[0]
        self.assertEqual(method, "setSMS")
        self.assertEqual(params["did"], self.did.number[1:])
        self.assertEqual(params["enable"], 1)
        self.assertIn("/sms_voipms/inbound/tok?from={FROM}", params["url_callback"])
        self.assertEqual(params["url_callback_enabled"], 1)
        self.assertEqual(params["url_callback_retry"], 1)

    def test_configure_requires_token(self):
        """Without an inbound token the button refuses to configure."""
        self.env["ir.config_parameter"].sudo().set_str("sms_voipms.inbound_token", "")
        with self.assertRaises(UserError):
            self.company._configure_voipms_callback()
