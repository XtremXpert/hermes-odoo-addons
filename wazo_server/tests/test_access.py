# Part of the wazo_server Odoo module. See LICENSE for details.
"""Droits d'accès : la gestion des tenants est réservée aux gestionnaires.

Une fiche de tenant porte le **jeton d'API** et le **mot de passe
d'administration** du client : elle n'a rien à faire sous les yeux d'un
utilisateur ordinaire, et encore moins entre ses mains.
"""

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('wazo_server', 'post_install', '-at_install')
class TestTenantAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tenant = cls.env['wazo.server.tenant'].create({
            'name': 'Client Alpha', 'slug': 'alpha'})
        cls.gestionnaire = cls.env['res.users'].create({
            'name': 'Gestionnaire Wazo',
            'login': 'wazo_server_test_gestionnaire',
            'group_ids': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('wazo_phone.group_wazo_manager').id])],
        })
        cls.ordinaire = cls.env['res.users'].create({
            'name': 'Utilisateur ordinaire',
            'login': 'wazo_server_test_ordinaire',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    def test_manager_reads_writes_and_creates(self):
        gestionnaire = self.tenant.with_user(self.gestionnaire)
        self.assertEqual(gestionnaire.name, 'Client Alpha')
        gestionnaire.write({'name': 'Client Alpha 2'})
        nouveau = self.env['wazo.server.tenant'].with_user(
            self.gestionnaire).create({'name': 'Client Beta', 'slug': 'beta'})
        self.assertTrue(nouveau.id)

    def test_plain_user_cannot_read_a_tenant(self):
        with self.assertRaises(AccessError):
            self.tenant.with_user(self.ordinaire).name

    def test_plain_user_cannot_create_a_tenant(self):
        with self.assertRaises(AccessError):
            self.env['wazo.server.tenant'].with_user(self.ordinaire).create(
                {'name': 'Client Gamma', 'slug': 'gamma'})

    def test_plain_user_cannot_delete_a_tenant(self):
        with self.assertRaises(AccessError):
            self.tenant.with_user(self.ordinaire).unlink()
