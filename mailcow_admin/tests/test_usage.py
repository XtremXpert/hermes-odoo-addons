# Ce que Mailcow sait de chaque boîte et que le module ignorait :
# le quota consommé, le nombre de messages, et les dernières connexions.
# Les horodatages de l'API sont des entiers Unix, parfois 0 (= jamais).
from datetime import UTC
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..services.mailcow_client import MailcowClient

ENTREE = {
    "username": "sonde@dc.com",
    "local_part": "sonde",
    "domain": "dc.com",
    "active": 1,
    "name": "Sonde",
    "description": "",
    "quota": 1073741824,  # 1 Gio, en octets
    "quota_used": 87857,  # 87 Ko : une valeur qui n'est pas ronde
    "percent_in_use": "25",  # Mailcow l'envoie en texte
    "percent_class": "success",
    "messages": 42,
    "last_imap_login": 1758000000,
    "last_smtp_login": 1758000000,
    "last_pop3_login": 0,  # 0 = jamais
}


class TestUsageDesBoites(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain = cls.env["mailcow.domain"].search([("name", "=", "dc.com")], limit=1)
        if not cls.domain:
            cls.domain = cls.env["mailcow.domain"].create({"name": "dc.com"})

    def _synchroniser(self, entree=None):
        with patch.object(
            MailcowClient, "_request", return_value=[entree if entree is not None else ENTREE]
        ):
            self.env["mailcow.mailbox"].action_sync_all_from_mailcow()
        return self.env["mailcow.mailbox"].search(
            [("local_part", "=", "sonde"), ("domain_id", "=", self.domain.id)], limit=1
        )

    def test_lit_le_quota_consomme_et_le_nombre_de_messages(self):
        boite = self._synchroniser()
        # 87 857 octets = 0,08 Mo. Une valeur ronde (256 Mo) ne verrait pas
        # un arrondi fautif ; celle-ci le montre.
        self.assertAlmostEqual(boite.quota_used_mb, 0.08, places=2)
        self.assertEqual(boite.messages, 42)

    def test_lit_l_occupation_meme_quand_elle_arrive_en_texte(self):
        boite = self._synchroniser()
        self.assertAlmostEqual(boite.percent_in_use, 25.0, places=1)

    def test_convertit_les_connexions_en_date_utilisable(self):
        boite = self._synchroniser()
        self.assertTrue(boite.last_imap_login)
        # On vérifie l'aller-retour plutôt qu'une date écrite à la main.
        self.assertEqual(
            int(boite.last_imap_login.replace(tzinfo=UTC).timestamp()),
            1758000000,
        )

    def test_un_horodatage_nul_veut_dire_jamais(self):
        boite = self._synchroniser()
        self.assertFalse(boite.last_pop3_login)

    def test_une_entree_vide_ne_casse_rien(self):
        """Mailcow répond parfois [{}] : ce n'est pas une boîte."""
        boite = self._synchroniser(entree={})
        self.assertFalse(boite)
        self.assertEqual(
            self.env["mailcow.mailbox"].search_count([("domain_id", "=", self.domain.id)]), 0
        )
