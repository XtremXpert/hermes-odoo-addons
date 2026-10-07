# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Tests des accès : groupe utilisateur en lecture seule, gestionnaire en écriture."""

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("wazo_phone", "post_install", "-at_install")
class TestWazoAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_user = cls.env.ref("wazo_phone.group_wazo_user")
        cls.group_manager = cls.env.ref("wazo_phone.group_wazo_manager")
        cls.manager = cls.env["res.users"].create(
            {"name": "Gest Wazo", "login": "gest.wazo", "email": "gest.wazo@example.com"}
        )
        cls.manager.group_ids = [(4, cls.group_manager.id)]
        cls.viewer = cls.env["res.users"].create(
            {"name": "Lect Wazo", "login": "lect.wazo", "email": "lect.wazo@example.com"}
        )
        cls.viewer.group_ids = [(4, cls.group_user.id)]

    def test_manager_can_create_wazo_user(self):
        record = (
            self.env["wazo.user"]
            .with_user(self.manager)
            .create({"name": "Test", "extension": "100"})
        )
        self.assertTrue(record.id)

    def test_viewer_cannot_create_wazo_user(self):
        with self.assertRaises(AccessError):
            self.env["wazo.user"].with_user(self.viewer).create(
                {"name": "Interdit", "extension": "101"}
            )

    def test_viewer_cannot_read_sip_password(self):
        record = (
            self.env["wazo.user"]
            .with_user(self.manager)
            .create({"name": "Secret", "extension": "102", "sip_password": "topsecret"})
        )
        with self.assertRaises(AccessError):
            record.with_user(self.viewer).read(["sip_password"])

    def test_viewer_cannot_write_wazo_user(self):
        record = (
            self.env["wazo.user"]
            .with_user(self.manager)
            .create({"name": "Cible", "extension": "103"})
        )
        with self.assertRaises(AccessError):
            record.with_user(self.viewer).write({"name": "Modifié"})

    def test_viewer_can_read_cdr(self):
        self.env["wazo.cdr"].with_user(self.viewer).search([])

    def test_user_without_group_cannot_read_cdr(self):
        outsider = self.env["res.users"].create(
            {"name": "Hors Wazo", "login": "hors.wazo", "email": "hors.wazo@example.com"}
        )
        with self.assertRaises(AccessError):
            self.env["wazo.cdr"].with_user(outsider).search([])

    def test_manager_can_read_cdr(self):
        # Lecture par le gestionnaire est autorisée (peut être vide).
        self.env["wazo.cdr"].with_user(self.manager).search([])

    def test_manager_can_create_wazo_ring_group(self):
        record = (
            self.env["wazo.ring.group"]
            .with_user(self.manager)
            .create({"name": "Groupe Test", "extension": "205"})
        )
        self.assertTrue(record.id)

    def test_viewer_cannot_create_wazo_ring_group(self):
        with self.assertRaises(AccessError):
            self.env["wazo.ring.group"].with_user(self.viewer).create(
                {"name": "Interdit", "extension": "206"}
            )

    def test_viewer_can_read_wazo_ring_group(self):
        self.env["wazo.ring.group"].with_user(self.manager).create(
            {"name": "Lisible", "extension": "207"}
        )
        self.env["wazo.ring.group"].with_user(self.viewer).search([])
