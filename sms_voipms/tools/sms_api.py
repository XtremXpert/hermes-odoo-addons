# Part of the sms_voipms Odoo module. See LICENSE for details.
"""VoIP.ms implementation of Odoo's SMS provider API.

Odoo 20 lets a company pick its SMS provider through
``res.company._get_sms_api_class`` and ``sms.sms._split_by_api``.  This class
implements the same contract as ``sms_twilio`` but talks to the VoIP.ms REST
API with the client and the segmentation rules already shipped by
``voipms_sms``.
"""

from odoo.addons.sms.tools.sms_api import SmsApiBase
from odoo.addons.voipms_sms.services.sms_segmentation import normalize_nanp
from odoo.addons.voipms_sms.services.sms_segmentation import split_sms
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSAPIError
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSClient


class SmsApiVoIPMS(SmsApiBase):
    """Send Odoo SMS through the VoIP.ms REST API."""

    def _send_sms_batch(self, messages, delivery_reports_url=False):
        """Send a batch of SMS through VoIP.ms.

        See :meth:`odoo.addons.sms.tools.sms_api.SmsApiBase._send_sms_batch`
        for the ``messages`` and results format.  The success state is
        ``sent`` (accepted by the provider), which Odoo maps to ``pending``.
        """
        company = (self.company or self.env.company).sudo()
        company._assert_sms_voipms_ready()
        did_number = company.sms_voipms_did_id.number
        client = VoIPMSClient(self.env)

        results = []
        for message in messages:
            body = message.get("content") or ""
            for number_info in message.get("numbers") or []:
                results.append(
                    self._send_one(
                        client,
                        did_number,
                        number_info["uuid"],
                        number_info["number"],
                        body,
                    )
                )
        return results

    def _send_one(self, client, did_number, uuid, number, body):
        """Send one SMS (possibly several segments) and return its result."""
        try:
            destination = normalize_nanp(number)
        except ValueError:
            return {
                "uuid": uuid,
                "state": "wrong_number_format",
                "failure_reason": self.env._("Numéro hors NANP : %s", number),
            }
        try:
            segments = split_sms(body)
        except ValueError as error:
            return {
                "uuid": uuid,
                "state": "server_error",
                "failure_reason": str(error),
            }

        message_ids = []
        try:
            for segment in segments:
                response = client._request(
                    "sendSMS",
                    {
                        "did": did_number,
                        "dst": destination,
                        "message": segment,
                    },
                )
                provider_id = response.get("message_id") or response.get("sms")
                if provider_id is not None:
                    message_ids.append(str(provider_id))
        except VoIPMSAPIError as error:
            return {
                "uuid": uuid,
                "state": "server_error",
                "failure_reason": str(error),
            }
        return {
            "uuid": uuid,
            "state": "sent",
            "sms_voipms_message_ids": ", ".join(message_ids),
        }
