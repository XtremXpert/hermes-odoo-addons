# Part of the voipms_sms Odoo module. See LICENSE for details.
"""Tests du modèle voipms.did (DID : numéro d'émetteur)."""

from unittest.mock import patch

from odoo.addons.voipms_sms.services.voipms_client import VoIPMSClient
from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("voipms_sms", "post_install", "-at_install")
class TestVoIPMSDid(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_str("voipms.api_username", "test-user")
        cls.env["ir.config_parameter"].sudo().set_str("voipms.api_token", "test-token")

    def test_sync_creates_remote_dids(self):
        remote = {
            "status": "success",
            "did": [
                {"did": "14184803381", "sms_available": 1, "sms_enabled": "1"},
                {"did": "15140000001", "sms_available": 1, "sms_enabled": "0"},
            ],
        }
        did = self.env["voipms.did"].create({"number": "14184803381"})
        with patch.object(VoIPMSClient, "_request", return_value=remote):
            did.action_sync_from_provider()
        self.assertEqual(
            len(self.env["voipms.did"].search([("number", "in", ["14184803381", "15140000001"])])),
            2,
        )
        first = self.env["voipms.did"].search([("number", "=", "14184803381")])
        self.assertEqual(first.sms_enabled, 1)
        self.assertTrue(first.synced)

    def test_duplicate_number_rejected(self):
        self.env["voipms.did"].create({"number": "14184803381"})
        with self.assertRaises(UserError):
            self.env["voipms.did"].create({"number": "14184803381"})

    def test_number_normalized_on_create(self):
        did = self.env["voipms.did"].create({"number": "4184803381"})
        self.assertEqual(did.number, "14184803381")
