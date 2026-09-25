# Part of the voipms_sms Odoo module. See LICENSE for details.
"""Tests des réglages de connexion VoIP.ms."""

from unittest.mock import patch

from odoo.addons.voipms_sms.services.voipms_client import VoIPMSClient
from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged('voipms_sms', 'post_install', '-at_install')
class TestVoIPMSSettings(TransactionCase):

    def test_settings_store_credentials(self):
        settings = self.env['res.config.settings'].create({})
        settings.voipms_api_username = 'myuser'
        settings.voipms_api_token = 'mytoken'
        settings.execute()
        icp = self.env['ir.config_parameter'].sudo()
        self.assertEqual(icp.get_str('voipms.api_username'), 'myuser')
        self.assertEqual(icp.get_str('voipms.api_token'), 'mytoken')

    def test_test_connection_success(self):
        self.env['ir.config_parameter'].sudo().set_str(
            'voipms.api_username', 'test-user')
        self.env['ir.config_parameter'].sudo().set_str(
            'voipms.api_token', 'test-token')
        settings = self.env['res.config.settings'].create({})
        with patch.object(
            VoIPMSClient, '_request',
            return_value={'status': 'success'},
        ):
            settings.action_test_voipms_connection()
        self.assertTrue(settings.voipms_connection_ok)

    def test_test_connection_failure(self):
        from odoo.addons.voipms_sms.services.voipms_client import VoIPMSAPIError
        self.env['ir.config_parameter'].sudo().set_str(
            'voipms.api_username', 'test-user')
        self.env['ir.config_parameter'].sudo().set_str(
            'voipms.api_token', 'test-token')
        settings = self.env['res.config.settings'].create({})
        with patch.object(
            VoIPMSClient, '_request',
            side_effect=VoIPMSAPIError('IP not enabled'),
        ):
            with self.assertRaises(UserError):
                settings.action_test_voipms_connection()
        self.assertFalse(settings.voipms_connection_ok)
