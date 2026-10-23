# Part of the wazo_server Odoo module. See LICENSE for details.
"""Tableau de bord de l'exploitant : agrégats croisés tenants / pont.

Le solde VoIP.ms se lit **sur demande seulement** — un chargement de page
n'appelle jamais le fournisseur. Les tests moquent ``VoIPMSClient`` là où
il est importé (les classes du registre Odoo sont read-only, un
``patch.object`` y échoue — même leçon que dans wazo_voipms).
"""

from datetime import datetime
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

from odoo import fields
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSAPIError
from odoo.tests import TransactionCase
from odoo.tests import tagged

#: Point de construction du client VoIP.ms dans le modèle du tableau.
VOIPMS_CTOR = (
    "odoo.addons.wazo_server.models.wazo_server_dashboard.VoIPMSClient"
)


@tagged("wazo_server", "post_install", "-at_install")
class TestServerDashboard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Dashboard = cls.env["wazo.server.dashboard"]
        cls.Tenant = cls.env["wazo.server.tenant"]
        cls.Trunk = cls.env["wazo.voipms.trunk"]
        cls.Did = cls.env["voipms.did"]

    def _dashboard(self):
        return self.Dashboard.get_server_dashboard()

    def test_aggregates_tenants_trunks_and_dids(self):
        self.Tenant.create({"name": "Diverse-Cité", "slug": "diverse"})
        self.Trunk.create(
            {"name": "T1", "voipms_username": "u", "voipms_password": "p"}
        )
        self.Did.create({"number": "4184803381"})
        data = self._dashboard()
        self.assertEqual(data["tenants"]["total"], 1)
        self.assertEqual(data["tenants"]["states"].get("new"), 1)
        self.assertEqual(len(data["trunks"]["items"]), 1)
        self.assertEqual(data["trunks"]["items"][0]["name"], "T1")
        self.assertEqual(data["dids"]["total"], 1)
        self.assertEqual(data["dids"]["muted"], 1)
        self.assertEqual(data["dids"]["routed"], 0)

    def test_did_routed_counts(self):
        did = self.Did.create({"number": "4184803382"})
        did.wazo_route_state = "routed"
        data = self._dashboard()
        self.assertEqual(data["dids"]["routed"], 1)
        self.assertEqual(data["dids"]["muted"], 0)

    def test_token_expiry_flags_only_soon(self):
        bientot = fields.Datetime.to_string(
            datetime.now() + timedelta(days=10)
        )
        loin = fields.Datetime.to_string(
            datetime.now() + timedelta(days=200)
        )
        self.Tenant.create(
            {"name": "Bientôt", "slug": "bientot", "token_expires_at": bientot}
        )
        self.Tenant.create(
            {"name": "Loin", "slug": "loin", "token_expires_at": loin}
        )
        data = self._dashboard()
        self.assertEqual(data["tenants"]["expiring"], 1)
        noms = {
            item["name"]: item["expires_soon"] for item in data["tenants"]["items"]
        }
        self.assertTrue(noms["Bientôt"])
        self.assertFalse(noms["Loin"])

    def test_no_balance_call_by_default(self):
        """Sans ``with_balance``, aucune requête au fournisseur."""
        client = MagicMock()
        with patch(VOIPMS_CTOR, return_value=client):
            data = self._dashboard()
        self.assertIsNone(data["balance"])
        client._request.assert_not_called()

    def test_balance_on_request_parses_amount(self):
        client = MagicMock()
        client._request.return_value = {
            "status": "success",
            "balance": {"current_balance": "7.107500"},
        }
        with patch(VOIPMS_CTOR, return_value=client):
            data = self.Dashboard.get_server_dashboard(with_balance=True)
        client._request.assert_called_once_with("getBalance")
        self.assertEqual(data["balance"]["amount"], "7.11")
        self.assertIsNone(data["balance"]["error"])

    def test_balance_failure_degrades_gracefully(self):
        """Un fournisseur muet ne casse pas le tableau de bord.

        Le modèle n'attrape que ``VoIPMSAPIError`` — un autre exception
        serait un bug et doit remonter.
        """
        client = MagicMock()
        client._request.side_effect = VoIPMSAPIError("réseau")
        with patch(VOIPMS_CTOR, return_value=client):
            data = self.Dashboard.get_server_dashboard(with_balance=True)
        self.assertIsNone(data["balance"]["amount"])
        self.assertTrue(data["balance"]["error"])
        # Le reste du tableau reste lisible.
        self.assertEqual(data["tenants"]["total"], 0)

    def test_balance_unreadable_response_degrades(self):
        client = MagicMock()
        client._request.return_value = {"status": "success", "balance": {}}
        with patch(VOIPMS_CTOR, return_value=client):
            data = self.Dashboard.get_server_dashboard(with_balance=True)
        self.assertIsNone(data["balance"]["amount"])
        self.assertTrue(data["balance"]["error"])
