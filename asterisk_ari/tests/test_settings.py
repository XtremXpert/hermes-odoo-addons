# Part of the asterisk_ari Odoo module. See LICENSE for details.
"""Tests des réglages de connexion Asterisk ARI."""

from unittest.mock import patch

from odoo.addons.asterisk_ari.services.ari_client import ARI
from odoo.addons.asterisk_ari.services.ari_client import ARIError
from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("asterisk_ari", "post_install", "-at_install")
class TestAsteriskSettings(TransactionCase):
    def test_settings_store_credentials(self):
        settings = self.env["res.config.settings"].create({})
        settings.asterisk_base_url = "http://pbx:8088/ari"
        settings.asterisk_app_name = "odoo_click"
        settings.asterisk_api_token = "s3cret"
        settings.execute()
        icp = self.env["ir.config_parameter"].sudo()
        self.assertEqual(icp.get_str("asterisk_ari.base_url"), "http://pbx:8088/ari")
        self.assertEqual(icp.get_str("asterisk_ari.app_name"), "odoo_click")
        self.assertEqual(icp.get_str("asterisk_ari.api_token"), "s3cret")

    def test_test_connection_success(self):
        self.env["ir.config_parameter"].sudo().set_str(
            "asterisk_ari.base_url", "http://pbx:8088/ari"
        )
        self.env["ir.config_parameter"].sudo().set_str("asterisk_ari.app_name", "odoo_click")
        self.env["ir.config_parameter"].sudo().set_str("asterisk_ari.api_token", "s3cret")
        settings = self.env["res.config.settings"].create({})
        with patch.object(ARI, "list_apps", return_value=["odoo_click"]) as list_apps:
            settings.action_test_ari_connection()
        list_apps.assert_called_once()
        self.assertTrue(settings.asterisk_connection_ok)

    def test_test_connection_failure(self):
        self.env["ir.config_parameter"].sudo().set_str(
            "asterisk_ari.base_url", "http://pbx:8088/ari"
        )
        self.env["ir.config_parameter"].sudo().set_str("asterisk_ari.app_name", "odoo_click")
        self.env["ir.config_parameter"].sudo().set_str("asterisk_ari.api_token", "wrong")
        settings = self.env["res.config.settings"].create({})
        with patch.object(
            ARI,
            "list_apps",
            side_effect=ARIError("Erreur ARI 401 : Unauthorized"),
        ):
            with self.assertRaises(UserError) as ctx:
                settings.action_test_ari_connection()
        self.assertIn("401", str(ctx.exception))
        self.assertFalse(settings.asterisk_connection_ok)
