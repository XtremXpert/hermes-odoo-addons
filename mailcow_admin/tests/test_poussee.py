# Pousser vers Mailcow ce qui existe localement : ce qui manque est créé,
# ce qui est connu est mis à jour. Une seule action pour tout un lot.
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..services.mailcow_client import MailcowClient

REPONSE = [{"msg": "Task completed", "type": "success"}]


class TestPoussee(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain = cls.env["mailcow.domain"].search([("name", "=", "dc.com")], limit=1)
        if not cls.domain:
            cls.domain = cls.env["mailcow.domain"].create({"name": "dc.com"})

    def test_cree_ce_qui_manque_et_met_a_jour_le_reste(self):
        nouvelle = self.env["mailcow.mailbox"].create(
            {
                "local_part": "nouvelle",
                "domain_id": self.domain.id,
                "password": "Un-mot-de-passe-1",
            }
        )
        connue = self.env["mailcow.mailbox"].create(
            {
                "local_part": "connue",
                "domain_id": self.domain.id,
                "synced": True,
            }
        )
        with patch.object(MailcowClient, "_request", return_value=REPONSE) as appel:
            (nouvelle | connue).action_push_to_mailcow()
        chemins = [a[0][1] for a in appel.call_args_list if a[0][0] == "POST"]
        self.assertIn("/add/mailbox", chemins, "la nouvelle boîte aurait dû être créée")
        self.assertIn("/edit/mailbox", chemins, "la boîte connue aurait dû être mise à jour")
        self.assertTrue(nouvelle.synced)
        self.assertTrue(connue.synced)

    def test_ne_touche_pas_au_serveur_pour_une_fiche_archivee(self):
        """Une fiche archivée a été supprimée du serveur : on n'y revient pas."""
        ancienne = self.env["mailcow.mailbox"].create(
            {
                "local_part": "ancienne",
                "domain_id": self.domain.id,
                "synced": True,
                "active": False,
            }
        )
        with patch.object(MailcowClient, "_request", return_value=REPONSE) as appel:
            ancienne.action_push_to_mailcow()
        appel.assert_not_called()
