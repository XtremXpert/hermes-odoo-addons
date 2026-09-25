# Part of the asterisk_ari Odoo module. See LICENSE for details.
"""Tests des droits d'accès du module asterisk_ari."""

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged('asterisk_ari', 'post_install', '-at_install')
class TestAsteriskAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        GroupUser = cls.env.ref('asterisk_ari.group_asterisk_user')
        cls.external_user = cls.env['res.users'].create({
            'name': 'Ext Tel',
            'login': 'ext.tel',
            'email': 'ext.tel@example.com',
        })
        cls.external_user.group_ids = [(4, GroupUser.id)]

    def test_user_without_group_cannot_read(self):
        outsider = self.env['res.users'].create({
            'name': 'Outsider',
            'login': 'outsider.tel',
            'email': 'outsider@example.com',
        })
        with self.assertRaises(AccessError):
            self.env['asterisk.call'].with_user(outsider).search([])

    def test_user_in_group_can_create(self):
        call = self.env['asterisk.call'].with_user(self.external_user).create({
            'phone': '5551234',
        })
        self.assertTrue(call.id)
