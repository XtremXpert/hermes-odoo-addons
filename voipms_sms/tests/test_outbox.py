# Part of the voipms_sms Odoo module. See LICENSE for details.
"""Tests de la boîte d'envoi SMS : segmentation, normalisation, statuts, erreurs."""

from unittest.mock import patch

from odoo.addons.voipms_sms.services.voipms_client import VoIPMSAPIError
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSClient
from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged('voipms_sms', 'post_install', '-at_install')
class TestVoIPMSOutbox(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_str(
            'voipms.api_username', 'test-user')
        cls.env['ir.config_parameter'].sudo().set_str(
            'voipms.api_token', 'test-token')
        cls.did = cls.env['voipms.did'].create({
            'number': '14184803381',
            'sms_enabled': 1,
        })

    def _make_message(self, body, dst='14184541752'):
        return self.env['voipms.sms.out'].create({
            'did_id': self.did.id,
            'destination': dst,
            'body': body,
        })

    def test_send_short_message_marks_sent(self):
        msg = self._make_message('Bonjour')
        with patch.object(
            VoIPMSClient, '_request',
            return_value={'status': 'success', 'message_id': 7},
        ) as request:
            msg.action_send()
        request.assert_called_once()
        self.assertEqual(request.call_args[0][0], 'sendSMS')
        payload = request.call_args[0][1]
        self.assertEqual(payload['did'], '14184803381')
        self.assertEqual(payload['dst'], '14184541752')
        self.assertEqual(payload['message'], 'Bonjour')
        self.assertEqual(msg.state, 'sent')
        self.assertEqual(msg.provider_message_ids, '7')

    def test_long_message_sends_numbered_segments(self):
        long_body = ' '.join(['mot%d' % i for i in range(60)])  # > 150 car.
        msg = self._make_message(long_body)
        with patch.object(
            VoIPMSClient, '_request',
            return_value={'status': 'success', 'message_id': 8},
        ) as request:
            msg.action_send()
        self.assertGreater(request.call_count, 1)
        first = request.call_args_list[0][0][1]['message']
        self.assertTrue(first.startswith('1/%d ' % request.call_count))
        self.assertEqual(msg.state, 'sent')

    def test_send_requires_sms_enabled_did(self):
        did_no_sms = self.env['voipms.did'].create({
            'number': '15140000001', 'sms_enabled': 0})
        msg = self.env['voipms.sms.out'].create({
            'did_id': did_no_sms.id,
            'destination': '14184541752',
            'body': 'Bonjour',
        })
        with self.assertRaises(UserError):
            msg.action_send()

    def test_send_rejects_empty_body(self):
        msg = self._make_message('   ')
        with self.assertRaises(UserError):
            msg.action_send()

    def test_send_rejects_malformed_destination(self):
        msg = self._make_message('Bonjour', dst='123')
        with self.assertRaises(UserError):
            msg.action_send()

    def test_send_failure_marks_failed_and_keeps_message(self):
        msg = self._make_message('Bonjour')
        with patch.object(
            VoIPMSClient, '_request',
            side_effect=VoIPMSAPIError('IP not enabled'),
        ):
            msg.action_send()
        self.assertEqual(msg.state, 'failed')
        self.assertEqual(msg.body, 'Bonjour')
        self.assertEqual(msg.error_message, 'IP not enabled')

    def test_destination_is_normalized_before_send(self):
        msg = self._make_message('Bonjour', dst='4184541752')
        with patch.object(
            VoIPMSClient, '_request',
            return_value={'status': 'success', 'message_id': 9},
        ) as request:
            msg.action_send()
        self.assertEqual(request.call_args[0][1]['dst'], '14184541752')
