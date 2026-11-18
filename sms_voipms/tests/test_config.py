# Part of the sms_voipms Odoo module. See LICENSE for details.

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase

from .common import SmsVoipmsCommon


class TestConfig(SmsVoipmsCommon, TransactionCase):
    def test_company_refuses_voipms_without_did(self):
        """The company constraint refuses a missing DID."""
        with self.assertRaises(ValidationError):
            self.company.write({"sms_voipms_did_id": False})

    def test_settings_view_is_inherited(self):
        """The settings view carries the provider radio."""
        view = self.env.ref("sms_voipms.res_config_settings_view_form")
        self.assertIn("sms_provider", view.arch)

    def test_admin_can_read_dids(self):
        """The administrator can read DID records."""
        admin = self.env.ref("base.user_admin")
        dids = self.env["voipms.did"].with_user(admin).search([("id", "=", self.did.id)])
        self.assertEqual(dids, self.did)
