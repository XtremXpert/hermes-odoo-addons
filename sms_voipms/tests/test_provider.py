# Part of the sms_voipms Odoo module. See LICENSE for details.

from odoo.addons.sms.tools.sms_api import SmsApi
from odoo.addons.sms_voipms.tools.sms_api import SmsApiVoIPMS
from odoo.tests import TransactionCase

from .common import SmsVoipmsCommon


class TestProvider(SmsVoipmsCommon, TransactionCase):
    def test_default_provider_is_iap(self):
        """The default provider stays the Odoo IAP service."""
        defaults = self.env["res.company"].default_get(["sms_provider"])
        self.assertEqual(defaults["sms_provider"], "iap")

    def test_api_class_follows_provider(self):
        """The company returns the API class matching its provider."""
        self.assertIs(self.company._get_sms_api_class(), SmsApiVoIPMS)
        self.company.sms_provider = "iap"
        self.assertIs(self.company._get_sms_api_class(), SmsApi)

    def test_split_by_api_routes_voipms(self):
        """A voipms company is routed to SmsApiVoIPMS."""
        sms = self._new_sms()
        batches = list(sms._split_by_api())
        self.assertEqual(len(batches), 1)
        api, records = batches[0]
        self.assertIsInstance(api, SmsApiVoIPMS)
        self.assertEqual(records, sms)

    def test_split_by_api_keeps_iap(self):
        """An iap company keeps the stock IAP API class."""
        self.company.sms_provider = "iap"
        sms = self._new_sms()
        batches = list(sms._split_by_api())
        self.assertEqual(len(batches), 1)
        api, records = batches[0]
        self.assertIsInstance(api, SmsApi)
        self.assertEqual(records, sms)
