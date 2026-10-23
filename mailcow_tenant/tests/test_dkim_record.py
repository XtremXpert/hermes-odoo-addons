# L'enregistrement DKIM à publier dans le DNS : la partie PUBLIQUE
# seulement. La clé privée ne doit ni s'afficher ni se ranger dans Odoo.
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from ..services.mailcow_client import MailcowClient

REPONSE = [{"msg": "Task completed", "type": "success"}]


class TestEnregistrementDkim(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domaine = cls.env["mailcow.domain"].create({"name": "dkim.com", "synced": True})

    def test_ne_garde_que_la_partie_publique(self):
        reponse = [
            {
                "dkim_selector": "dkim",
                "dkim_txt": "v=DKIM1;k=rsa;p=CLE-PUBLIQUE",
                "pubkey": "CLE-PUBLIQUE",
                "privkey": "CLE-PRIVEE-A-NE-JAMAIS-EXPOSER",
            }
        ]
        with patch.object(MailcowClient, "_request", return_value=reponse):
            self.domaine.action_fetch_dkim()
        self.assertIn("CLE-PUBLIQUE", self.domaine.dkim_record)
        self.assertIn("dkim._domainkey.dkim.com", self.domaine.dkim_record)
        self.assertNotIn("PRIVEE", self.domaine.dkim_record)

    def test_le_selecteur_du_serveur_est_respecte(self):
        reponse = [{"dkim_selector": "selecteur2", "dkim_txt": "v=DKIM1;p=X"}]
        with patch.object(MailcowClient, "_request", return_value=reponse):
            self.domaine.action_fetch_dkim()
        self.assertIn("selecteur2._domainkey.dkim.com", self.domaine.dkim_record)

    def test_refuse_une_reponse_sans_cle(self):
        with patch.object(MailcowClient, "_request", return_value=[{"type": "danger"}]):
            with self.assertRaises(UserError):
                self.domaine.action_fetch_dkim()
