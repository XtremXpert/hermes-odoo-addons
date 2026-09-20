# Part of the mailcow_admin Odoo module. See LICENSE for details.
"""Tests des actions push/pull sur mailcow.mailbox et du wizard de mot de passe."""

from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.mailcow_admin.services.mailcow_client import MailcowClient


@tagged('mailcow_admin', 'post_install', '-at_install')
class TestMailcowMailbox(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_str(
            'mailcow.base_url', 'https://mail.example.com')
        cls.env['ir.config_parameter'].sudo().set_str(
            'mailcow.api_key', 'test-api-key')
        cls.domain = cls.env['mailcow.domain'].create({'name': 'dc.com'})

    def test_email_is_computed(self):
        mailbox = self.env['mailcow.mailbox'].create({
            'local_part': 'info',
            'domain_id': self.domain.id,
        })
        self.assertEqual(mailbox.email, 'info@dc.com')

    def test_create_on_mailcow_requires_password(self):
        mailbox = self.env['mailcow.mailbox'].create({
            'local_part': 'info',
            'domain_id': self.domain.id,
        })
        with self.assertRaises(UserError):
            mailbox.action_create_on_mailcow()

    def test_create_on_mailcow_sends_payload_and_marks_synced(self):
        mailbox = self.env['mailcow.mailbox'].create({
            'local_part': 'info',
            'domain_id': self.domain.id,
            'name': 'Info Diverse',
            'quota_mb': 100,
        })
        mailbox.password = 'S3cret!'
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'mailbox_added', 'type': 'success'}],
        ) as request:
            mailbox.action_create_on_mailcow()
        request.assert_called_once_with('POST', '/add/mailbox', {
            'mail_user': 'info',
            'domain': 'dc.com',
            'password': 'S3cret!',
            'password2': 'S3cret!',
            'quota': 102400,
            'active': '1',
            'name': 'Info Diverse',
            'description': '',
            'tls_enforce_in': '1',
            'tls_enforce_out': '1',
        })
        self.assertTrue(mailbox.synced)

    def test_update_on_mailcow_does_not_send_password(self):
        mailbox = self.env['mailcow.mailbox'].create({
            'local_part': 'info',
            'domain_id': self.domain.id,
            'synced': True,
            'quota_mb': 50,
        })
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'mailbox_updated', 'type': 'success'}],
        ) as request:
            mailbox.action_update_on_mailcow()
        payload = request.call_args[0][2]
        request.assert_called_once()
        self.assertNotIn('password', payload)
        self.assertNotIn('password2', payload)
        self.assertEqual(request.call_args[0][1], '/edit/mailbox')
        self.assertEqual(payload['quota'], 51200)

    def test_delete_on_mailcow_unsyncs_and_archives(self):
        mailbox = self.env['mailcow.mailbox'].create({
            'local_part': 'info',
            'domain_id': self.domain.id,
            'synced': True,
        })
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'mailbox_deleted', 'type': 'success'}],
        ) as request:
            mailbox.action_delete_on_mailcow()
        request.assert_called_once_with(
            'POST', '/delete/mailbox', {'mail_user': 'info', 'domain': 'dc.com'})
        self.assertFalse(mailbox.synced)
        self.assertFalse(mailbox.active)

    def test_sync_from_mailbox_creates_and_unsyncs_local_only(self):
        local_only = self.env['mailcow.mailbox'].create({
            'local_part': 'local',
            'domain_id': self.domain.id,
            'synced': True,
        })
        remote = {'data': [
            {
                'mail_user': 'info',
                'domain': 'dc.com',
                'name': 'Info',
                'description': '',
                'active': '1',
                'quota': 102400,
            },
            {
                'mail_user': 'support',
                'domain': 'other.com',
                'name': '',
                'description': '',
                'active': '0',
                'quota': 0,
            },
        ]}
        with patch.object(MailcowClient, '_request', return_value=remote) as request:
            local_only.action_sync_from_mailcow()
        request.assert_called_once_with('GET', '/get/mailbox/111', None)

        info = self.env['mailcow.mailbox'].search(
            [('local_part', '=', 'info'), ('domain_id.name', '=', 'dc.com')])
        self.assertTrue(info)
        self.assertEqual(info.quota_mb, 100)
        self.assertTrue(info.synced)

        # Le domaine inconnu est créé à la volée
        support = self.env['mailcow.mailbox'].with_context(
            active_test=False).search([('local_part', '=', 'support')])
        self.assertTrue(support)
        self.assertEqual(support.domain_id.name, 'other.com')
        self.assertFalse(support.active)

        local_only = local_only.search([('local_part', '=', 'local')])
        self.assertFalse(local_only.synced)

    def test_reset_password_wizard_sends_new_password(self):
        mailbox = self.env['mailcow.mailbox'].create({
            'local_part': 'info',
            'domain_id': self.domain.id,
            'synced': True,
        })
        wizard = self.env['mailcow.mailbox.password'].create({
            'mailbox_id': mailbox.id,
            'password': 'N3wPass!',
            'confirm': 'N3wPass!',
        })
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'mailbox_updated', 'type': 'success'}],
        ) as request:
            wizard.action_reset()
        payload = request.call_args[0][2]
        self.assertEqual(request.call_args[0][1], '/edit/mailbox')
        self.assertEqual(payload['password'], 'N3wPass!')
        self.assertEqual(payload['password2'], 'N3wPass!')
        self.assertTrue(mailbox.synced)

    def test_reset_password_mismatch_raises(self):
        mailbox = self.env['mailcow.mailbox'].create({
            'local_part': 'info',
            'domain_id': self.domain.id,
        })
        with self.assertRaises(ValidationError):
            self.env['mailcow.mailbox.password'].create({
                'mailbox_id': mailbox.id,
                'password': 'une',
                'confirm': 'deux',
            })
