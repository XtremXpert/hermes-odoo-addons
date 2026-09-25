# Part of the asterisk_ari Odoo module. See LICENSE for details.
"""Tests du bouton click-to-call sur res.partner."""

from unittest.mock import patch

from odoo.addons.asterisk_ari.services.ari_client import ARI
from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged('asterisk_ari', 'post_install', '-at_install')
class TestPartnerClickToCall(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_str(
            'asterisk_ari.base_url', 'http://pbx:8088/ari')
        cls.env['ir.config_parameter'].sudo().set_str(
            'asterisk_ari.app_name', 'odoo_click')
        cls.env['ir.config_parameter'].sudo().set_str(
            'asterisk_ari.api_token', 'tok')

    def test_click_to_call_creates_and_originates(self):
        partner = self.env['res.partner'].create({
            'name': 'Alice',
            'phone': '5551234',
        })
        with patch.object(ARI, 'originate',
                          return_value={'id': 'call-9'}):
            call = partner.action_click_to_call()
        self.assertEqual(call.partner_id, partner)
        self.assertEqual(call.phone, '5551234')
        self.assertEqual(call.state, 'ringing')
        self.assertEqual(call.ari_call_id, 'call-9')

    def test_click_to_call_requires_phone(self):
        partner = self.env['res.partner'].create({'name': 'NoNum'})
        with self.assertRaises(UserError):
            partner.action_click_to_call()
