# Part of the mailcow_admin Odoo module. See LICENSE for details.
"""Tests des actions push/pull sur mailcow.mailbox et de ses mots de passe."""

from unittest.mock import patch

from odoo.addons.mailcow_admin.services.mailcow_client import MailcowClient
from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("mailcow_admin", "post_install", "-at_install")
class TestMailcowMailbox(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_str(
            "mailcow.base_url", "https://mail.example.com"
        )
        cls.env["ir.config_parameter"].sudo().set_str("mailcow.api_key", "test-api-key")
        cls.domain = cls.env["mailcow.domain"].create({"name": "dc.com"})

    def test_email_is_computed(self):
        mailbox = self.env["mailcow.mailbox"].create(
            {
                "local_part": "info",
                "domain_id": self.domain.id,
            }
        )
        self.assertEqual(mailbox.email, "info@dc.com")

    def test_create_generates_password_shown_once_and_never_stored(self):
        self.assertNotIn("password", self.env["mailcow.mailbox"]._fields)
        mailbox = self.env["mailcow.mailbox"].create(
            {
                "local_part": "info",
                "domain_id": self.domain.id,
            }
        )
        with patch.object(MailcowClient, "_request", return_value=[{"type": "success"}]) as request:
            action = mailbox.action_create_on_mailcow()
        envoye = request.call_args[0][2]["password"]
        self.assertGreaterEqual(len(envoye), 20)
        self.assertEqual(request.call_args[0][2]["password2"], envoye)
        self.assertIn("info@dc.com : " + envoye, action["params"]["message"])
        self.assertTrue(action["params"]["sticky"])
        self.assertNotIn(envoye, " ".join(mailbox.message_ids.mapped("body")))

    def test_failed_create_shows_no_password(self):
        mailbox = self.env["mailcow.mailbox"].create(
            {
                "local_part": "info",
                "domain_id": self.domain.id,
            }
        )
        with patch.object(MailcowClient, "_request", side_effect=UserError("refus")):
            with self.assertRaises(UserError):
                mailbox.action_create_on_mailcow()
        self.assertFalse(mailbox.synced)

    def test_create_on_mailcow_sends_payload_and_marks_synced(self):
        mailbox = self.env["mailcow.mailbox"].create(
            {
                "local_part": "info",
                "domain_id": self.domain.id,
                "name": "Info Diverse",
                "quota_mb": 100,
            }
        )
        with (
            patch.object(type(mailbox), "_nouveau_mot_de_passe", return_value="S3cret!"),
            patch.object(
                MailcowClient,
                "_request",
                return_value=[{"msg": "mailbox_added", "type": "success"}],
            ) as request,
        ):
            mailbox.action_create_on_mailcow()
        request.assert_called_once_with(
            "POST",
            "/add/mailbox",
            {
                "local_part": "info",
                "domain": "dc.com",
                "password": "S3cret!",
                "password2": "S3cret!",
                "quota": 100,  # Mailcow attend des mébioctets
                "active": "1",
                "name": "Info Diverse",
                "description": "",
                "tls_enforce_in": "1",
                "tls_enforce_out": "1",
            },
        )
        self.assertTrue(mailbox.synced)

    def test_update_on_mailcow_does_not_send_password(self):
        mailbox = self.env["mailcow.mailbox"].create(
            {
                "local_part": "info",
                "domain_id": self.domain.id,
                "synced": True,
                "quota_mb": 50,
            }
        )
        with patch.object(
            MailcowClient,
            "_request",
            return_value=[{"msg": "mailbox_updated", "type": "success"}],
        ) as request:
            mailbox.action_update_on_mailcow()
        payload = request.call_args[0][2]
        request.assert_called_once()
        self.assertEqual(request.call_args[0][1], "/edit/mailbox")
        # Mailcow attend {"items": [...], "attr": {...}} : un corps plat est
        # accepté puis ignoré, sans la moindre erreur.
        self.assertEqual(payload["items"], ["info@dc.com"])
        self.assertNotIn("password", payload["attr"])
        self.assertNotIn("password2", payload["attr"])
        self.assertEqual(payload["attr"]["quota"], 50)

    def test_delete_on_mailcow_unsyncs_and_archives(self):
        mailbox = self.env["mailcow.mailbox"].create(
            {
                "local_part": "info",
                "domain_id": self.domain.id,
                "synced": True,
            }
        )
        with patch.object(
            MailcowClient,
            "_request",
            return_value=[{"msg": "mailbox_deleted", "type": "success"}],
        ) as request:
            mailbox.action_delete_on_mailcow()
        # Mailcow exige l'adresse complète pour supprimer une boîte :
        # « local_part » + « domain » lui vaut un access_denied.
        request.assert_called_once_with("POST", "/delete/mailbox", {"mail_user": "info@dc.com"})
        self.assertFalse(mailbox.synced)
        self.assertFalse(mailbox.active)

    def test_sync_from_mailbox_creates_and_unsyncs_local_only(self):
        local_only = self.env["mailcow.mailbox"].create(
            {
                "local_part": "local",
                "domain_id": self.domain.id,
                "synced": True,
            }
        )
        # Forme réelle de /get/mailbox/all : « username » et « local_part »,
        # et non « mail_user » (relevé sur le serveur le 24 septembre 2026).
        remote = {
            "data": [
                {
                    "username": "info@dc.com",
                    "local_part": "info",
                    "domain": "dc.com",
                    "name": "Info",
                    "description": "",
                    "active": "1",
                    "quota": 104857600,
                },
                {
                    "username": "support@other.com",
                    "local_part": "support",
                    "domain": "other.com",
                    "name": "",
                    "description": "",
                    "active": "0",
                    "quota": 0,
                },
            ]
        }
        with patch.object(MailcowClient, "_request", return_value=remote) as request:
            local_only.action_sync_from_mailcow()
        request.assert_called_once_with("GET", "/get/mailbox/all", None)

        info = self.env["mailcow.mailbox"].search(
            [("local_part", "=", "info"), ("domain_id.name", "=", "dc.com")]
        )
        self.assertTrue(info)
        self.assertEqual(info.quota_mb, 100)
        self.assertTrue(info.synced)

        # Le domaine inconnu est créé à la volée
        support = (
            self.env["mailcow.mailbox"]
            .with_context(active_test=False)
            .search([("local_part", "=", "support")])
        )
        self.assertTrue(support)
        self.assertEqual(support.domain_id.name, "other.com")
        self.assertFalse(support.active)

        local_only = local_only.search([("local_part", "=", "local")])
        self.assertFalse(local_only.synced)

    def test_reset_password_sends_generated_password_shown_once(self):
        mailbox = self.env["mailcow.mailbox"].create(
            {
                "local_part": "info",
                "domain_id": self.domain.id,
                "synced": True,
            }
        )
        with patch.object(
            MailcowClient,
            "_request",
            return_value=[{"msg": "mailbox_updated", "type": "success"}],
        ) as request:
            action = mailbox.action_reset_password()
        payload = request.call_args[0][2]
        self.assertEqual(request.call_args[0][1], "/edit/mailbox")
        self.assertEqual(payload["items"], ["info@dc.com"])
        nouveau = payload["attr"]["password"]
        self.assertEqual(payload["attr"]["password2"], nouveau)
        self.assertIn("info@dc.com : " + nouveau, action["params"]["message"])
        self.assertNotIn(nouveau, " ".join(mailbox.message_ids.mapped("body")))
        self.assertNotIn("mailcow.mailbox.password", self.env)

    def test_sync_all_works_without_any_local_record(self):
        """Amorcer une base vide : le domaine inconnu est créé à la volée."""
        remote = {
            "data": [
                {
                    "username": "info@dc.com",
                    "local_part": "info",
                    "domain": "dc.com",
                    "name": "Info",
                    "description": "",
                    "active": "1",
                    "quota": 104857600,
                },
            ]
        }
        with patch.object(MailcowClient, "_request", return_value=remote):
            self.env["mailcow.mailbox"].action_sync_all_from_mailcow()
        boite = self.env["mailcow.mailbox"].search(
            [("local_part", "=", "info"), ("domain_id.name", "=", "dc.com")]
        )
        self.assertTrue(boite)
        self.assertEqual(boite.quota_mb, 100)  # octets relus en mébioctets
        self.assertTrue(boite.synced)
