# Le journal par fiche : qui, quand, et ce qui a été poussé vers Mailcow.
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..services.mailcow_client import MailcowClient

REPONSE = [{"msg": "Task completed", "type": "success"}]


class TestJournal(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain = cls.env["mailcow.domain"].search([("name", "=", "dc.com")], limit=1)
        if not cls.domain:
            cls.domain = cls.env["mailcow.domain"].create({"name": "dc.com"})

    def test_la_creation_poussee_laisse_une_trace(self):
        boite = self.env["mailcow.mailbox"].create(
            {
                "local_part": "trace",
                "domain_id": self.domain.id,
                "password": "Un-mot-de-passe-1",
            }
        )
        with patch.object(MailcowClient, "_request", return_value=REPONSE):
            boite.action_push_to_mailcow()
        corps = " ".join(boite.message_ids.mapped("body"))
        self.assertIn("Mailcow", corps, "aucune trace de la poussée")
        self.assertIn("trace@dc.com", corps, "la fiche n est pas nommée")

    def test_la_modification_poussee_laisse_une_trace(self):
        boite = self.env["mailcow.mailbox"].create(
            {"local_part": "trace2", "domain_id": self.domain.id, "synced": True}
        )
        with patch.object(MailcowClient, "_request", return_value=REPONSE):
            boite.action_push_to_mailcow()
        corps = " ".join(boite.message_ids.mapped("body"))
        self.assertIn("Mise à jour", corps, "aucune mention de mise à jour")

    def test_la_suppression_laisse_une_trace(self):
        boite = self.env["mailcow.mailbox"].create(
            {"local_part": "trace3", "domain_id": self.domain.id, "synced": True}
        )
        with patch.object(MailcowClient, "_request", return_value=REPONSE):
            boite.action_delete_on_mailcow()
        corps = " ".join(boite.message_ids.mapped("body"))
        self.assertIn("supprim", corps.lower(), "aucune trace de la suppression")

    def test_l_auteur_est_l_utilisateur_courant(self):
        boite = self.env["mailcow.mailbox"].create(
            {"local_part": "trace4", "domain_id": self.domain.id, "password": "Un-mot-de-passe-1"}
        )
        with patch.object(MailcowClient, "_request", return_value=REPONSE):
            boite.action_push_to_mailcow()
        # L'auteur d'un message est un partenaire : celui de l'utilisateur.
        self.assertEqual(boite.message_ids[0].author_id, self.env.user.partner_id)
