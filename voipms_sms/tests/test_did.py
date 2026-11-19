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
        """Prépare les identifiants VoIP.ms des tests de DID."""
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_str("voipms.api_username", "test-user")
        cls.env["ir.config_parameter"].sudo().set_str("voipms.api_token", "test-token")

    def test_sync_creates_remote_dids(self):
        """Vérifie que la synchronisation crée les DID distants."""
        remote = {
            "status": "success",
            "dids": [
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
        """Vérifie qu'un numéro en double est refusé."""
        self.env["voipms.did"].create({"number": "14184803381"})
        with self.assertRaises(UserError):
            self.env["voipms.did"].create({"number": "14184803381"})

    def test_number_normalized_on_create(self):
        """Vérifie que le numéro est normalisé à la création."""
        did = self.env["voipms.did"].create({"number": "4184803381"})
        self.assertEqual(did.number, "14184803381")

    def test_sync_works_on_empty_table_uses_dids(self):
        """Vérifie que la synchro modèle fonctionne sans aucun DID local."""
        remote = {
            "status": "success",
            "dids": [
                {"did": "14184803381", "sms_available": 1, "sms_enabled": "1"},
            ],
        }
        self.assertEqual(self.env["voipms.did"].search_count([]), 0)
        with patch.object(VoIPMSClient, "_request", return_value=remote):
            self.env["voipms.did"].sync_from_provider()
        did = self.env["voipms.did"].search([("number", "=", "14184803381")])
        self.assertTrue(did)
        self.assertEqual(did.sms_enabled, 1)
        self.assertTrue(did.synced)

    def test_sync_falls_back_to_legacy_did_key(self):
        """Vérifie que l'ancienne clé ``did`` reste lue."""
        remote = {
            "status": "success",
            "did": [{"did": "14184803381", "sms_available": 1, "sms_enabled": "1"}],
        }
        with patch.object(VoIPMSClient, "_request", return_value=remote):
            self.env["voipms.did"].sync_from_provider()
        self.assertTrue(self.env["voipms.did"].search([("number", "=", "14184803381")]))
