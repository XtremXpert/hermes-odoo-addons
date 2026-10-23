# Le bouton « Fourre-tout » d'une boîte : le fourre-tout du domaine pointe
# vers elle, qu'il existe déjà ou non. Un fourre-tout est un alias
# dont l'adresse est « @domaine ».
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from ..services.mailcow_client import MailcowClient

REPONSE = [{"msg": "Task completed", "type": "success"}]


class TestBoutonFourreTout(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain = cls.env["mailcow.domain"].search([("name", "=", "dc.com")], limit=1)
        if not cls.domain:
            cls.domain = cls.env["mailcow.domain"].create({"name": "dc.com"})

    def _boite(self, local="bouton", synced=True):
        return self.env["mailcow.mailbox"].create(
            {
                "local_part": local,
                "domain_id": self.domain.id,
                "synced": synced,
            }
        )

    def _fourre_tout(self):
        return self.env["mailcow.alias"].search(
            [("domain_id", "=", self.domain.id), ("is_catch_all", "=", True)]
        )

    def test_cree_le_fourre_tout_absent(self):
        boite = self._boite()
        with patch.object(MailcowClient, "_request", return_value=REPONSE):
            boite.action_make_catch_all()
        self.assertEqual(len(self._fourre_tout()), 1)
        self.assertEqual(self._fourre_tout().address_ids.mapped("address"), ["bouton@dc.com"])
        self.assertTrue(self._fourre_tout().synced)

    def test_reoriente_un_fourre_tout_existant(self):
        boite = self._boite()
        autre = self.env["mailcow.email_address"].create({"address": "autre@dc.com"})
        existant = self.env["mailcow.alias"].create(
            {
                "domain_id": self.domain.id,
                "is_catch_all": True,
                "address_ids": [(6, 0, [autre.id])],
                "synced": True,
                "mailcow_id": "55",
            }
        )
        with patch.object(MailcowClient, "_request", return_value=REPONSE):
            boite.action_make_catch_all()
        self.assertEqual(existant.address_ids.mapped("address"), ["bouton@dc.com"])
        self.assertEqual(len(self._fourre_tout()), 1)
        self.assertTrue(existant.synced)

    def test_refuse_une_boite_absente_du_serveur(self):
        boite = self._boite(local="fantome", synced=False)
        with self.assertRaises(UserError):
            boite.action_make_catch_all()
