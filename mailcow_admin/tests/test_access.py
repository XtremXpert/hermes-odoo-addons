# Part of the mailcow_admin Odoo module. See LICENSE for details.
"""Tests des droits d'accès du module Mailcow Admin."""

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("mailcow_admin", "post_install", "-at_install")
class TestMailcowAccessRights(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain = cls.env["mailcow.domain"].create({"name": "rights.com"})
        # Utilisateur standard, sans aucun groupe Mailcow
        cls.external_user = cls.env["res.users"].create(
            {
                "name": "Sans accès Mailcow",
                "login": "mailcow_no_access",
            }
        )
        cls.manager_user = cls.env.ref("mailcow_admin.group_mailcow_manager").user_ids[0]

    def test_external_user_cannot_read_domains(self):
        with self.assertRaises(AccessError):
            self.env["mailcow.domain"].with_user(self.external_user).search([])

    def test_external_user_cannot_create_mailbox(self):
        with self.assertRaises(AccessError):
            self.env["mailcow.mailbox"].with_user(self.external_user).create(
                {
                    "local_part": "x",
                    "domain_id": self.domain.id,
                }
            )

    def test_manager_can_read_domains(self):
        domains = self.env["mailcow.domain"].with_user(self.manager_user).search([])
        self.assertIn(self.domain, domains)

    def test_regular_user_without_group_cannot_unlink(self):
        with self.assertRaises(AccessError):
            self.domain.with_user(self.external_user).unlink()
