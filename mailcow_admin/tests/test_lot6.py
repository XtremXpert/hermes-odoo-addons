# Ce que le serveur offre vraiment : sa version, et les mots de passe
# applicatifs — fabriqués par nous, montrés une fois, jamais rangés.
#
# La réponse simulée est celle que le serveur a réellement renvoyée : elle ne
# contient aucun mot de passe. Un test qui l'inventerait passerait sur du vide.
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..services.mailcow_client import MailcowClient

SECRET = "Mot-de-passe-application-42"
CHEMIN_FABRIQUE = (
    "odoo.addons.mailcow_admin.wizards.mailcow_app_password_wizard.secrets.token_urlsafe"
)


class TestVersionDuServeur(TransactionCase):
    def test_le_test_de_connexion_annonce_la_version(self):
        def repondre(methode, chemin, *args, **kwargs):
            if chemin.endswith("/version"):
                return [{"version": "2025-09b"}]
            return [{"domain_name": "dc.com"}]

        with patch.object(MailcowClient, "_request", side_effect=repondre) as appel:
            action = self.env["res.config.settings"].action_test_mailcow_connection()
        self.assertIn(
            "2025-09b", action["params"]["message"], "la version du serveur n est pas annoncée"
        )
        self.assertIn(
            "domaine", action["params"]["message"].lower(), "le test ne dit plus rien des domaines"
        )
        self.assertIn("/get/status/version", [c.args[1] for c in appel.call_args_list])


class TestMotDePasseApplication(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain = cls.env["mailcow.domain"].search([("name", "=", "dc.com")], limit=1)
        if not cls.domain:
            cls.domain = cls.env["mailcow.domain"].create({"name": "dc.com"})
        cls.boite = cls.env["mailcow.mailbox"].create(
            {"local_part": "appli", "domain_id": cls.domain.id, "synced": True}
        )

    def _reponse_reelle(self):
        """La forme exacte renvoyée par Mailcow 2025-09b : sans mot de passe."""
        return [
            {
                "type": "success",
                "msg": "app_passwd_added",
                "log": [
                    {
                        "active": "1",
                        "app_name": "wordpress",
                        "username": self.boite.email,
                        "protocols": ["imap_access"],
                    }
                ],
            }
        ]

    def _assistant(self, **extra):
        valeurs = {"mailbox_id": self.boite.id, "app_name": "wordpress"}
        valeurs.update(extra)
        return self.env["mailcow.app.password.wizard"].create(valeurs)

    def test_le_mot_de_passe_montre_est_celui_envoye(self):
        """Le serveur ne rend jamais le mot de passe : celui montré doit être
        exactement celui que nous avons fabriqué et transmis."""
        with patch(CHEMIN_FABRIQUE, return_value=SECRET):
            with patch.object(
                MailcowClient, "_request", return_value=self._reponse_reelle()
            ) as appel:
                action = self._assistant().action_create_app_password()
        charge = appel.call_args_list[0].args[2]
        self.assertEqual(charge["app_passwd"], SECRET)
        self.assertEqual(
            charge["app_passwd2"], SECRET, "la confirmation doit porter le même mot de passe"
        )
        self.assertIn(
            SECRET,
            action["params"]["message"],
            "le mot de passe n est pas montré à l administrateur",
        )

    def test_le_mot_de_passe_n_est_range_nulle_part(self):
        with patch(CHEMIN_FABRIQUE, return_value=SECRET):
            with patch.object(MailcowClient, "_request", return_value=self._reponse_reelle()):
                self._assistant().action_create_app_password()
        valeurs = " ".join(str(v) for v in self.boite.read()[0].values())
        self.assertNotIn(SECRET, valeurs, "le mot de passe est resté dans la boîte")
        corps = " ".join(self.boite.message_ids.mapped("body"))
        self.assertNotIn(SECRET, corps, "le mot de passe a été journalisé")

    def test_le_geste_est_journalise(self):
        with patch(CHEMIN_FABRIQUE, return_value=SECRET):
            with patch.object(MailcowClient, "_request", return_value=self._reponse_reelle()):
                self._assistant().action_create_app_password()
        corps = " ".join(self.boite.message_ids.mapped("body"))
        self.assertIn("wordpress", corps, "le geste n est pas noté dans le fil")

    def test_la_demande_porte_les_bons_champs(self):
        with patch(CHEMIN_FABRIQUE, return_value=SECRET):
            with patch.object(
                MailcowClient, "_request", return_value=self._reponse_reelle()
            ) as appel:
                self._assistant().action_create_app_password()
        chemin = appel.call_args_list[0].args[1]
        charge = appel.call_args_list[0].args[2]
        self.assertEqual(chemin, "/add/app-passwd")
        self.assertEqual(charge["username"], self.boite.email)
        self.assertEqual(charge["app_name"], "wordpress")
        self.assertEqual(charge["active"], "1")
        self.assertEqual(len(charge["protocols"]), 6, "tous les protocoles ne sont pas demandés")
        self.assertEqual(
            charge["app_passwd"], SECRET, "le mot de passe fabriqué n est pas celui envoyé"
        )

    def test_le_nom_est_obligatoire(self):
        with patch.object(MailcowClient, "_request", return_value=self._reponse_reelle()) as appel:
            self._assistant(app_name="").action_create_app_password()
        self.assertFalse(appel.called, "un appel a été fait sans nom")
