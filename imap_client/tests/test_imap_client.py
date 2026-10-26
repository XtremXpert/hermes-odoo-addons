# Part of the imap_client Odoo module. See LICENSE for details.
"""Client IMAP : connexion, dossiers, messages — imaplib moque."""

from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestImapClient(TransactionCase):
    """Le client rapatrie dossiers et messages."""

    def setUp(self):
        super().setUp()
        self.compte = self.env["imap.account"].create(
            {
                "name": "boite",
                "host": "imap.test",
                "user": "me@test",
                "password": "secret",
            }
        )

    def test_la_sync_des_dossiers_cree_les_fiches(self):
        """Les dossiers du serveur deviennent des fiches."""
        with patch("odoo.addons.imap_client.models.imap_account.IMAPConnexion") as connexion:
            instance = connexion.return_value
            instance.dossiers.return_value = ["INBOX", "Envoyes"]
            instance.quitter.return_value = None
            self.compte.action_sync()
        dossiers = self.env["imap.folder"].search([("account_id", "=", self.compte.id)])
        self.assertEqual(sorted(dossiers.mapped("name")), ["Envoyes", "INBOX"])
