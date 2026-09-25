# Part of the asterisk_ari Odoo module. See LICENSE for details.
"""Tests du modèle asterisk.call (origination, hangup, échecs)."""

from unittest.mock import patch

from odoo.addons.asterisk_ari.services.ari_client import ARI
from odoo.addons.asterisk_ari.services.ari_client import ARIError
from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged('asterisk_ari', 'post_install', '-at_install')
class TestAsteriskCall(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_str(
            'asterisk_ari.base_url', 'http://pbx:8088/ari')
        cls.env['ir.config_parameter'].sudo().set_str(
            'asterisk_ari.app_name', 'odoo_click')
        cls.env['ir.config_parameter'].sudo().set_str(
            'asterisk_ari.api_token', 'tok')

    def _call(self, phone='5551234'):
        return self.env['asterisk.call'].create({'phone': phone})

    def test_originate_sets_ringing_and_call_id(self):
        call = self._call()
        with patch.object(
            ARI, 'originate', return_value={'id': 'call-1'}
        ) as originate:
            call.action_originate()
        originate.assert_called_once()
        self.assertEqual(call.state, 'ringing')
        self.assertEqual(call.ari_call_id, 'call-1')
        self.assertTrue(call.date_started)

    def test_originate_uses_pjsip_endpoint(self):
        call = self._call('5551234')
        with patch.object(ARI, 'originate',
                          return_value={'id': 'call-1'}) as originate:
            call.action_originate()
        self.assertEqual(originate.call_args[0][0], 'PJSIP/5551234')

    def test_originate_requires_phone(self):
        call = self.env['asterisk.call'].create({'phone': '  '})
        with self.assertRaises(UserError):
            call.action_originate()

    def test_originate_marks_failed_on_ari_error(self):
        call = self._call()
        with patch.object(
            ARI, 'originate',
            side_effect=ARIError('Erreur ARI 500 : bad gateway'),
        ):
            call.action_originate()
        self.assertEqual(call.state, 'failed')
        self.assertIn('500', call.error_message)

    def test_hangup_sets_ended(self):
        call = self._call()
        call.write({'state': 'ringing', 'ari_call_id': 'call-1'})
        with patch.object(ARI, 'hangup') as hangup:
            call.action_hangup()
        hangup.assert_called_once_with('call-1')
        self.assertEqual(call.state, 'ended')
        self.assertTrue(call.date_ended)

    def test_hangup_requires_call_id(self):
        call = self._call()
        with self.assertRaises(UserError):
            call.action_hangup()
