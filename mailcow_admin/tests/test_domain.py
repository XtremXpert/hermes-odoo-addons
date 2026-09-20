# Part of the mailcow_admin Odoo module. See LICENSE for details.
"""Tests des actions push/pull sur mailcow.domain."""

from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.mailcow_admin.services.mailcow_client import MailcowClient


@tagged('mailcow_admin', 'post_install', '-at_install')
class TestMailcowDomain(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_str(
            'mailcow.base_url', 'https://mail.example.com')
        cls.env['ir.config_parameter'].sudo().set_str(
            'mailcow.api_key', 'test-api-key')

    def test_create_on_mailcow_sends_domain_and_marks_synced(self):
        domain = self.env['mailcow.domain'].create({
            'name': 'dc.com',
            'description': 'Mon domaine',
            'quota_mb': 100,
            'dkim': True,
        })
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'domain_added', 'type': 'success'}],
        ) as request:
            domain.action_create_on_mailcow()
        request.assert_called_once_with('POST', '/add/domain', {
            'domain': 'dc.com',
            'description': 'Mon domaine',
            'dkim': True,
            'quota': 102400,
        })
        self.assertTrue(domain.synced)

    def test_update_on_mailcow_sends_edit_payload(self):
        domain = self.env['mailcow.domain'].create(
            {'name': 'dc.com', 'synced': True})
        domain.description = 'Description mise à jour'
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'domain_updated', 'type': 'success'}],
        ) as request:
            domain.action_update_on_mailcow()
        request.assert_called_once_with('POST', '/edit/domain', {
            'domain': 'dc.com',
            'description': 'Description mise à jour',
            'dkim': True,
            'quota': 0,
        })

    def test_delete_on_mailcow_unsyncs_and_archives(self):
        domain = self.env['mailcow.domain'].create(
            {'name': 'dc.com', 'synced': True})
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'domain_deleted', 'type': 'success'}],
        ) as request:
            domain.action_delete_on_mailcow()
        request.assert_called_once_with('POST', '/delete/domain', {'domain': 'dc.com'})
        self.assertFalse(domain.synced)
        self.assertFalse(domain.active)
        self.assertFalse(domain.mailboxes.synced)
        self.assertFalse(domain.aliases.synced)

    def test_sync_from_mailcow_creates_updates_and_unsyncs_local_only(self):
        local_only = self.env['mailcow.domain'].create(
            {'name': 'local-only.com', 'synced': True})
        existing = self.env['mailcow.domain'].create({
            'name': 'dc.com',
            'description': 'ancienne',
            'quota_mb': 50,
        })
        remote = {'data': [
            {
                'id': 'abc',
                'domain': 'dc.com',
                'description': 'nouvelle',
                'active': '1',
                'dkim': {'private': 'p', 'public': 'pub'},
                'quota': 204800,
            },
            {
                'id': 'def',
                'domain': 'new.com',
                'description': 'neuf',
                'active': '1',
                'dkim': None,
                'quota': 0,
            },
        ]}
        with patch.object(MailcowClient, '_request', return_value=remote) as request:
            existing.action_sync_from_mailcow()
        request.assert_called_once_with('GET', '/get/domain/111', None)

        existing = self.env['mailcow.domain'].search([('name', '=', 'dc.com')])
        self.assertEqual(existing.description, 'nouvelle')
        self.assertEqual(existing.quota_mb, 200)
        self.assertTrue(existing.dkim)
        self.assertTrue(existing.synced)
        self.assertEqual(existing.mailcow_id, 'abc')

        new_domain = self.env['mailcow.domain'].search([('name', '=', 'new.com')])
        self.assertTrue(new_domain)
        self.assertFalse(new_domain.dkim)
        self.assertTrue(new_domain.synced)

        local_only = local_only.search([('name', '=', 'local-only.com')])
        self.assertFalse(local_only.synced)
