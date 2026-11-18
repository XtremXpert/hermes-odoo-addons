# Part of the sms_voipms Odoo module. See LICENSE for details.

from unittest.mock import patch

from odoo.addons.sms.tools.sms_api import SmsApi
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSClient
from odoo.tests import TransactionCase

from .common import SmsVoipmsCommon


class TestSend(SmsVoipmsCommon, TransactionCase):
    def test_send_sms_batch_success(self):
        """One sendSMS call is made and the SMS reaches pending."""
        sms = self._new_sms(number="5145550101", body="Bonjour")
        response = {"status": "success", "message_id": "42"}
        with (
            patch.object(VoIPMSClient, "_request", return_value=response) as request,
            patch.object(SmsApi, "_contact_iap") as iap,
        ):
            sms.send()
        request.assert_called_once_with(
            "sendSMS",
            {"did": "15145550100", "dst": "15145550101", "message": "Bonjour"},
        )
        iap.assert_not_called()
        sms.invalidate_recordset()
        self.assertEqual(sms.state, "pending")
        self.assertFalse(sms.failure_type)

    def test_tracker_keeps_provider_ids(self):
        """The provider message id is kept on the sms.tracker."""
        sms = self._new_sms()
        tracker = self.env["sms.tracker"].create({"sms_uuid": sms.uuid})
        with patch.object(
            VoIPMSClient,
            "_request",
            return_value={"status": "success", "message_id": "7"},
        ):
            sms.send()
        tracker.invalidate_recordset()
        self.assertEqual(tracker.sms_voipms_message_ids, "7")

    def test_long_body_is_segmented(self):
        """A long body is split into numbered segments of 150 chars."""
        body = " ".join(["mot"] * 80)
        sms = self._new_sms(body=body)
        with patch.object(
            VoIPMSClient,
            "_request",
            return_value={"status": "success", "message_id": "1"},
        ) as request:
            sms.send()
        segments = [call.args[1]["message"] for call in request.call_args_list]
        self.assertGreater(len(segments), 1)
        self.assertTrue(all(len(segment) <= 150 for segment in segments))
        self.assertTrue(segments[0].startswith("1/"))
