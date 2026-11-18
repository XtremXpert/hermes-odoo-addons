# Part of the sms_voipms Odoo module. See LICENSE for details.

from unittest.mock import patch

from odoo.addons.sms_voipms.tools.sms_api import SmsApiVoIPMS
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSAPIError
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSClient
from odoo.exceptions import UserError
from odoo.tests import TransactionCase

from .common import SmsVoipmsCommon


class TestFailures(SmsVoipmsCommon, TransactionCase):
    def test_api_error_marks_sms_error(self):
        """A VoIP.ms error marks the SMS in error with the reason."""
        sms = self._new_sms()
        with patch.object(VoIPMSClient, "_request", side_effect=VoIPMSAPIError("refus VoIP.ms")):
            sms.send()
        sms.invalidate_recordset()
        self.assertEqual(sms.state, "error")
        self.assertEqual(sms.failure_type, "sms_server")

    def test_api_error_reason_is_reported(self):
        """The provider error text is carried in the batch result."""
        api = SmsApiVoIPMS(self.env)
        message = {
            "content": "Bonjour",
            "numbers": [{"number": "5145550101", "uuid": "a" * 32}],
        }
        with patch.object(VoIPMSClient, "_request", side_effect=VoIPMSAPIError("refus VoIP.ms")):
            results = api._send_sms_batch([message])
        self.assertEqual(results[0]["state"], "server_error")
        self.assertIn("refus VoIP.ms", results[0]["failure_reason"])

    def test_non_nanp_number_is_refused_locally(self):
        """A non-NANP number fails locally, without any call."""
        sms = self._new_sms(number="+33 6 12 34 56 78")
        with patch.object(VoIPMSClient, "_request") as request:
            sms.send()
        request.assert_not_called()
        sms.invalidate_recordset()
        self.assertEqual(sms.state, "error")
        self.assertEqual(sms.failure_type, "sms_number_format")

    def test_missing_did_raises_before_any_call(self):
        """A company without a DID cannot send at all."""
        self.env.cr.execute(
            "UPDATE res_company SET sms_voipms_did_id = NULL WHERE id = %s",
            (self.company.id,),
        )
        self.env.invalidate_all()
        sms = self._new_sms()
        with patch.object(VoIPMSClient, "_request") as request:
            with self.assertRaises(UserError):
                sms.send()
        request.assert_not_called()
