# Part of the voipms_sms Odoo module. See LICENSE for details.
"""Tests des droits d'accès du module voipms_sms."""

from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from odoo.addons.voipms_sms.services.voipms_client import VoIPMSClient


@tagged('voipms_sms', 'post_install', '-at_install')
class TestVoIPMSAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        GroupUser = cls.env.ref('voipms_sms.group_voipms_user')
        cls.external_user = cls.env['res.users'].create({
            'name': 'Ext SMS',
            'login': 'ext.sms',
            'email': 'ext.sms@example.com',
        })
        cls.external_user.group_ids = [(4, GroupUser.id)]

    def test_user_without_group_cannot_read(self):
        outsider = self.env['res.users'].create({
            'name': 'Outsider',
            'login': 'outsider.sms',
            'email': 'outsider@example.com',
        })
        with self.assertRaises(AccessError):
            self.env['voipms.sms.out'].with_user(outsider).search([])

    def test_regular_user_cannot_send(self):
        outsider = self.env['res.users'].create({
            'name': 'Outsider2',
            'login': 'outsider2.sms',
            'email': 'outsider2@example.com',
        })
        did = self.env['voipms.did'].create({'number': '14184803381'})
        msg = self.env['voipms.sms.out'].create({
            'did_id': did.id,
            'destination': '14184541752',
            'body': 'Bonjour',
        })
        with self.assertRaises(AccessError):
            msg.with_user(outsider).action_send()

    def test_regular_user_in_group_can_create_and_send(self):
        with patch.object(
            VoIPMSClient, '_request',
            return_value={'status': 'success', 'message_id': 1},
        ):
            did = self.env['voipms.did'].with_user(
                self.external_user).create(
                {'number': '14184803381', 'sms_enabled': 1})
            msg = self.env['voipms.sms.out'].with_user(
                self.external_user).create({
                'did_id': did.id,
                'destination': '14184541752',
                'body': 'Bonjour',
            })
            msg.action_send()
        self.assertEqual(msg.state, 'sent')