# Part of the mailcow_admin Odoo module. See LICENSE for details.
"""Tests des actions push/pull sur mailcow.alias."""

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.mailcow_admin.services.mailcow_client import MailcowClient


@tagged('mailcow_admin', 'post_install', '-at_install')
class TestMailcowAlias(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_str(
            'mailcow.base_url', 'https://mail.example.com')
        cls.env['ir.config_parameter'].sudo().set_str(
            'mailcow.api_key', 'test-api-key')
        cls.domain = cls.env['mailcow.domain'].create({'name': 'dc.com'})
        cls.addresses = cls.env['mailcow.email_address'].create([
            {'address': 'info@dc.com'},
            {'address': 'admin@dc.com'},
        ])

    def test_create_alias_sends_addresses_and_marks_synced(self):
        alias = self.env['mailcow.alias'].create({
            'alias_name': 'info',
            'domain_id': self.domain.id,
            'address_ids': [(6, 0, self.addresses.ids)],
            'description': "Alias d'information",
        })
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'alias_added', 'type': 'success'}],
        ) as request:
            alias.action_create_on_mailcow()
        request.assert_called_once_with('POST', '/add/alias', {
            'alias_name': 'info',
            'domain': 'dc.com',
            'address': ['info@dc.com', 'admin@dc.com'],
            'active': '1',
            'description': "Alias d'information",
        })
        self.assertTrue(alias.synced)

    def test_create_alias_requires_at_least_one_address(self):
        alias = self.env['mailcow.alias'].create({
            'alias_name': 'info',
            'domain_id': self.domain.id,
        })
        with self.assertRaises(UserError):
            alias.action_create_on_mailcow()

    def test_delete_alias_unsyncs_and_archives(self):
        alias = self.env['mailcow.alias'].create({
            'alias_name': 'info',
            'domain_id': self.domain.id,
            'synced': True,
        })
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'alias_deleted', 'type': 'success'}],
        ) as request:
            alias.action_delete_on_mailcow()
        request.assert_called_once_with(
            'POST', '/delete/alias', {'alias_name': 'info', 'domain': 'dc.com'})
        self.assertFalse(alias.synced)
        self.assertFalse(alias.active)

    def test_sync_from_mailcow_creates_missing_aliases(self):
        existing = self.env['mailcow.alias'].create({
            'alias_name': 'info',
            'domain_id': self.domain.id,
            'synced': True,
            'active': True,
        })
        # Forme réelle de /get/alias/all : « address » porte l'adresse de
        # l'alias, « goto » les destinations (relevé sur le serveur).
        remote = {'data': [
            {
                'address': 'info@dc.com',
                'domain': 'dc.com',
                'goto': ['info@dc.com'],
                'active': '0',
                'description': '',
            },
            {
                'address': 'support@dc.com',
                'domain': 'dc.com',
                'goto': ['info@dc.com'],
                'active': '1',
                'description': '',
            },
        ]}
        with patch.object(MailcowClient, '_request', return_value=remote) as request:
            existing.action_sync_from_mailcow()
        request.assert_called_once_with('GET', '/get/alias/all', None)

        # Recherche limitée au domaine du test : des alias réels portent déjà le
        # nom « info » (importés du serveur), et une recherche par nom seul
        # renverrait alors plusieurs fiches.
        existing = self.env['mailcow.alias'].with_context(
            active_test=False).search([
                ('alias_name', '=', 'info'),
                ('domain_id', '=', self.domain.id)])
        self.assertFalse(existing.active)
        self.assertEqual(
            existing.address_ids.mapped('address'), ['info@dc.com'])

        support = self.env['mailcow.alias'].search([
            ('alias_name', '=', 'support'),
            ('domain_id', '=', self.domain.id)])
        self.assertTrue(support)
        self.assertTrue(support.synced)
