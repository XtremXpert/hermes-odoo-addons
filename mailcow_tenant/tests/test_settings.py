# Part of the mailcow_tenant Odoo module. See LICENSE for details.
"""Tests du bouton de test de connexion dans les réglages."""

from unittest.mock import patch

from odoo.addons.mailcow_tenant.services.mailcow_client import MailcowAPIError
from odoo.addons.mailcow_tenant.services.mailcow_client import MailcowClient
from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("mailcow_tenant", "post_install", "-at_install")
class TestMailcowSettings(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_str(
            "mailcow.base_url", "https://mail.example.com"
        )
        cls.env["ir.config_parameter"].sudo().set_str("mailcow.api_key", "test-api-key")
        cls.settings = cls.env["res.config.settings"].create({})

    def test_connection_success_returns_success_notification(self):
        remote = {
            "data": [
                {"id": "a", "domain": "dc.com"},
                {"id": "b", "domain": "other.com"},
            ]
        }
        with patch.object(MailcowClient, "_request", return_value=remote):
            result = self.settings.action_test_mailcow_connection()
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")
        self.assertEqual(result["params"]["type"], "success")
        self.assertIn("2 domaine", result["params"]["message"])

    def test_connection_failure_raises_user_error(self):
        with patch.object(
            MailcowClient,
            "_request",
            side_effect=MailcowAPIError("Impossible de joindre Mailcow."),
        ):
            with self.assertRaises(UserError):
                self.settings.action_test_mailcow_connection()

    def test_connection_uses_the_listing_route(self):
        """La route de listage est `/all` : `111` répond 200 mais avec un corps vide."""
        with patch.object(
            MailcowClient,
            "_request",
            return_value={"data": []},
        ) as request:
            self.settings.action_test_mailcow_connection()
        appels = [appel.args for appel in request.call_args_list]
        self.assertIn(
            ("GET", "/get/domain/all"), appels, "la route de listage /all n'a pas été utilisée"
        )
        self.assertNotIn(
            "111",
            " ".join(chemin for _, chemin in appels),
            "une route par identifiant (111) a été utilisée, "
            "alors qu elle répond 200 avec un corps vide",
        )

    def test_connection_warns_when_the_server_returns_nothing(self):
        """Un corps vide ne doit jamais être annoncé comme un succès."""
        with patch.object(MailcowClient, "_request", return_value={"data": []}):
            result = self.settings.action_test_mailcow_connection()
        self.assertEqual(result["params"]["type"], "warning")
        self.assertIn("aucun domaine", result["params"]["message"].lower())
