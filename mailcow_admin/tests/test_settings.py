# Part of the mailcow_admin Odoo module. See LICENSE for details.
"""Tests du bouton de test de connexion dans les réglages."""

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.mailcow_admin.services.mailcow_client import (
    MailcowAPIError,
    MailcowClient,
)


@tagged('mailcow_admin', 'post_install', '-at_install')
class TestMailcowSettings(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_str(
            'mailcow.base_url', 'https://mail.example.com')
        cls.env['ir.config_parameter'].sudo().set_str(
            'mailcow.api_key', 'test-api-key')
        cls.settings = cls.env['res.config.settings'].create({})

    def test_connection_success_returns_success_notification(self):
        remote = {'data': [
            {'id': 'a', 'domain': 'dc.com'},
            {'id': 'b', 'domain': 'other.com'},
        ]}
        with patch.object(MailcowClient, '_request', return_value=remote):
            result = self.settings.action_test_mailcow_connection()
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')
        self.assertEqual(result['params']['type'], 'success')
        self.assertIn('2 domaine', result['params']['message'])

    def test_connection_failure_raises_user_error(self):
        with patch.object(
            MailcowClient, '_request',
            side_effect=MailcowAPIError('Impossible de joindre Mailcow.'),
        ):
            with self.assertRaises(UserError):
                self.settings.action_test_mailcow_connection()
