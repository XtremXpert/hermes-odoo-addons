# Part of the mailcow_admin Odoo module. See LICENSE for details.
"""Tests des actions push/pull sur mailcow.domain."""

from unittest.mock import patch

from odoo.addons.mailcow_admin.services.mailcow_client import MailcowClient
from odoo.tests import TransactionCase
from odoo.tests import tagged


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
        })
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'domain_added', 'type': 'success'}],
        ) as request:
            domain.action_create_on_mailcow()
        request.assert_called_once_with('POST', '/add/domain', {
            'domain': 'dc.com',
            'description': 'Mon domaine',
            'active': '1',
            # Mailcow compte les quotas en octets : 100 Mo = 104857600.
            'def_quota_for_mbox': 104857600,
            'max_quota_for_domain': 104857600,
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
        # quota_mb = 0 : aucun quota n'est envoyé, pour ne pas écraser la
        # politique de quotas du serveur.
        # Mailcow attend {"items": [...], "attr": {...}} : un corps plat est
        # accepté puis ignoré, sans la moindre erreur.
        request.assert_called_once_with('POST', '/edit/domain', {
            'items': ['dc.com'],
            'attr': {
                'description': 'Description mise à jour',
                'active': '1',
            },
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
        # Forme réelle de /get/domain/all : le nom du domaine est dans
        # « domain_name », et non « domain » (relevé sur le serveur).
        remote = {'data': [
            {
                'domain_name': 'dc.com',
                'description': 'nouvelle',
                'active': '1',
                'def_quota_for_mbox': 209715200,
            },
            {
                'id': 'def',
                'domain_name': 'new.com',
                'description': 'neuf',
                'active': '1',
                'def_quota_for_mbox': 0,
            },
        ]}
        with patch.object(MailcowClient, '_request', return_value=remote) as request:
            existing.action_sync_from_mailcow()
        request.assert_called_once_with('GET', '/get/domain/all', None)

        existing = self.env['mailcow.domain'].search([('name', '=', 'dc.com')])
        self.assertEqual(existing.description, 'nouvelle')
        self.assertEqual(existing.quota_mb, 200)
        self.assertTrue(existing.synced)

        new_domain = self.env['mailcow.domain'].search([('name', '=', 'new.com')])
        self.assertTrue(new_domain)
        self.assertTrue(new_domain.synced)

        local_only = local_only.search([('name', '=', 'local-only.com')])
        self.assertFalse(local_only.synced)

    def test_sync_all_works_without_any_local_record(self):
        """Amorcer une base vide : aucune fiche locale n'est nécessaire."""
        remote = {'data': [
            {'domain_name': 'dc.com', 'description': 'importé', 'active': '1'},
            {'domain_name': 'autre.com', 'description': '', 'active': '1'},
        ]}
        with patch.object(MailcowClient, '_request', return_value=remote):
            self.env['mailcow.domain'].action_sync_all_from_mailcow()
        self.assertEqual(
            sorted(self.env['mailcow.domain'].search(
                [('name', 'in', ['dc.com', 'autre.com'])]).mapped('name')),
            ['autre.com', 'dc.com'])
        self.assertTrue(self.env['mailcow.domain'].search(
            [('name', 'in', ['dc.com', 'autre.com'])]).mapped('synced'))
