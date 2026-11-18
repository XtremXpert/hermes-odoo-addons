# Part of the sms_voipms Odoo module. See LICENSE for details.

from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class SmsVoipmsCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Create a VoIP.ms DID and configure the test company."""
        super().setUpClass()
        cls.company = cls.env.company
        cls.did = cls.env["voipms.did"].create(
            {
                "number": "5145550100",
                "label": "Test",
                "sms_enabled": 1,
                "active": True,
            }
        )
        cls.company.write(
            {
                "sms_provider": "voipms",
                "sms_voipms_did_id": cls.did.id,
            }
        )
        parameters = cls.env["ir.config_parameter"].sudo()
        parameters.set_str("voipms.api_username", "test-user")
        parameters.set_str("voipms.api_token", "test-token")

    def _new_sms(self, number="5145550101", body="Bonjour"):
        return self.env["sms.sms"].create({"number": number, "body": body})
