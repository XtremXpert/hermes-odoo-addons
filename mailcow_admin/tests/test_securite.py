# Part of the mailcow_admin Odoo module. See LICENSE for details.
"""Constats de revue du 6 octobre 2026 : droits par méthode et écritures non rejouées."""

import urllib.error
from unittest.mock import patch

from odoo.addons.mailcow_admin.services.mailcow_client import MailcowAPIError
from odoo.addons.mailcow_admin.services.mailcow_client import MailcowClient
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase
from odoo.tests import tagged

from .test_robustesse import FausseReponse


class FichesMailcow(TransactionCase):
    """Un domaine, une boîte et un alias déjà sur le serveur, et des comptes."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.utilisateur = cls.env["res.users"].create(
            {
                "name": "Utilisateur Mailcow",
                "login": "mailcow_utilisateur_seul",
                "group_ids": [(6, 0, [cls.env.ref("mailcow_admin.group_mailcow_user").id])],
            }
        )
        cls.sans_groupe = cls.env["res.users"].create(
            {"name": "Sans Mailcow", "login": "mailcow_sans_groupe"}
        )
        cls.domaine = cls.env["mailcow.domain"].create({"name": "droits.test", "synced": True})
        cls.boite = cls.env["mailcow.mailbox"].create(
            {"local_part": "info", "domain_id": cls.domaine.id, "synced": True}
        )
        adresse = cls.env["mailcow.email_address"].create({"address": "info@droits.test"})
        cls.alias = cls.env["mailcow.alias"].create(
            {
                "alias_name": "contact",
                "domain_id": cls.domaine.id,
                "address_ids": [(6, 0, [adresse.id])],
                "synced": True,
            }
        )

    def _refuse(self, user, fiche, methode):
        with patch.object(MailcowClient, "_request", return_value=[]) as appel:
            with self.assertRaises(AccessError, msg=methode):
                getattr(fiche.with_user(user), methode)()
        appel.assert_not_called()


@tagged("mailcow_admin", "post_install", "-at_install")
class TestDroitsParMethode(FichesMailcow):
    """Le bouton masqué ne protège pas la méthode : chaque appel RPC est vérifié."""

    def test_utilisateur_ne_supprime_ni_ne_synchronise_sur_le_serveur(self):
        for fiche in (self.domaine, self.boite, self.alias):
            for methode in (
                "action_delete_on_mailcow",
                "action_sync_from_mailcow",
                "action_sync_all_from_mailcow",
                "action_preview_sync_from_mailcow",
                "action_purge_local",
            ):
                self._refuse(self.utilisateur, fiche, methode)

    def test_utilisateur_ne_change_pas_de_mot_de_passe(self):
        self._refuse(self.utilisateur, self.boite, "action_reset_password")
        self._refuse(self.utilisateur, self.boite, "action_create_app_password")

    def test_sans_groupe_aucun_appel_au_serveur(self):
        for fiche in (self.domaine, self.boite, self.alias):
            for methode in (
                "action_create_on_mailcow",
                "action_update_on_mailcow",
                "action_push_to_mailcow",
            ):
                self._refuse(self.sans_groupe, fiche, methode)
        self._refuse(self.sans_groupe, self.domaine, "action_fetch_dkim")
        self._refuse(self.sans_groupe, self.boite, "action_make_catch_all")

    def test_utilisateur_met_a_jour_sur_le_serveur(self):
        with patch.object(MailcowClient, "_request", return_value=[]) as appel:
            self.boite.with_user(self.utilisateur).action_update_on_mailcow()
        self.assertEqual(appel.call_args[0][1], "/edit/mailbox")

    def test_gestionnaire_supprime(self):
        gestionnaire = self.env.ref("mailcow_admin.group_mailcow_manager").user_ids[0]
        with patch.object(MailcowClient, "_request", return_value=[]) as appel:
            self.alias.with_user(gestionnaire).action_delete_on_mailcow()
        self.assertEqual(appel.call_args[0][1], "/delete/alias")


@tagged("mailcow_admin", "post_install", "-at_install")
class TestGroupeSynchronisation(FichesMailcow):
    """Le groupe des agents lit et synchronise, sans jamais écrire sur Mailcow."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env["res.users"].create(
            {
                "name": "Agent Mailcow",
                "login": "mailcow_agent_sync",
                "group_ids": [(6, 0, [cls.env.ref("mailcow_admin.group_mailcow_sync").id])],
            }
        )

    def test_synchronise_et_previsualise_en_lecture_seule(self):
        serveur = {"data": []}
        for fiche in (self.domaine, self.boite, self.alias):
            for methode in ("action_sync_all_from_mailcow", "action_sync_from_mailcow"):
                with patch.object(MailcowClient, "_request", return_value=serveur) as appel:
                    # Listage vide alors que des fiches existent : refus, sans rien marquer.
                    with self.assertRaises(MailcowAPIError):
                        getattr(fiche.with_user(self.agent), methode)()
                self.assertTrue(appel.call_args_list)
                self.assertEqual({a[0][0] for a in appel.call_args_list}, {"GET"})

    def test_la_synchronisation_ecrit_en_local(self):
        serveur = {
            "data": [
                {
                    "domain_name": "droits.test",
                    "active": "1",
                    "description": "Relue sur le serveur",
                }
            ]
        }
        with patch.object(MailcowClient, "_request", return_value=serveur) as appel:
            self.env["mailcow.domain"].with_user(self.agent).action_sync_all_from_mailcow()
        self.assertEqual({a[0][0] for a in appel.call_args_list}, {"GET"})
        self.assertEqual(self.domaine.description, "Relue sur le serveur")

    def test_apercu_lisible_par_l_agent(self):
        serveur = {"data": [{"domain_name": "neuf.test", "active": "1"}]}
        with patch.object(MailcowClient, "_request", return_value=serveur):
            action = (
                self.env["mailcow.domain"].with_user(self.agent).action_preview_sync_from_mailcow()
            )
        apercu = self.env["mailcow.sync.preview"].with_user(self.agent).browse(action["res_id"])
        self.assertIn("neuf.test", apercu.plan)
        self.assertFalse(self.env["mailcow.domain"].search([("name", "=", "neuf.test")]))

    def test_apercu_depuis_une_fiche(self):
        serveur = {"data": [{"domain_name": "neuf.test", "active": "1"}]}
        with patch.object(MailcowClient, "_request", return_value=serveur):
            action = self.domaine.with_user(self.agent).action_preview_sync()
        apercu = self.env["mailcow.sync.preview"].with_user(self.agent).browse(action["res_id"])
        self.assertIn("neuf.test", apercu.plan)
        self._refuse(self.utilisateur, self.domaine, "action_preview_sync")

    def test_aucune_ecriture_sur_le_serveur_ni_mot_de_passe(self):
        for fiche in (self.domaine, self.boite, self.alias):
            for methode in (
                "action_create_on_mailcow",
                "action_update_on_mailcow",
                "action_push_to_mailcow",
                "action_delete_on_mailcow",
                "action_purge_local",
                "action_forget_locally",
            ):
                self._refuse(self.agent, fiche, methode)
        for methode in (
            "action_reset_password",
            "action_create_app_password",
            "action_make_catch_all",
        ):
            self._refuse(self.agent, self.boite, methode)
        self._refuse(self.agent, self.domaine, "action_fetch_dkim")

    def test_aucune_ecriture_directe(self):
        boite = self.boite.with_user(self.agent)
        self.assertEqual(boite.email, "info@droits.test")
        with self.assertRaises(AccessError):
            boite.write({"quota_mb": 1})
        with self.assertRaises(AccessError):
            boite.unlink()
        with self.assertRaises(AccessError):
            self.env["mailcow.alias"].with_user(self.agent).create(
                {"alias_name": "x", "domain_id": self.domaine.id}
            )

    def test_utilisateur_ne_synchronise_toujours_pas_et_gestionnaire_si(self):
        self._refuse(self.utilisateur, self.domaine, "action_sync_all_from_mailcow")
        gestionnaire = self.env.ref("mailcow_admin.group_mailcow_manager").user_ids[0]
        self.assertTrue(gestionnaire.has_group("mailcow_admin.group_mailcow_sync"))


@tagged("mailcow_admin", "post_install", "-at_install")
class TestEcrituresNonRejouees(TransactionCase):
    def _client(self):
        return MailcowClient(self.env, base_url="https://exemple.test", api_key="clef-de-test")

    def test_une_ecriture_en_erreur_passagere_n_est_pas_rejouee(self):
        refus = urllib.error.HTTPError("https://exemple.test", 503, "Service Unavailable", {}, None)
        with patch("urllib.request.urlopen", side_effect=refus) as appel:
            with self.assertRaisesRegex(MailcowAPIError, "Résultat incertain"):
                self._client()._request("POST", "/add/alias", {"address": "a@b.test"})
        self.assertEqual(appel.call_count, 1)

    def test_une_ecriture_sans_reponse_n_est_pas_rejouee(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")) as appel:
            with self.assertRaisesRegex(MailcowAPIError, "Résultat incertain"):
                self._client()._request("POST", "/delete/alias", ["1"])
        self.assertEqual(appel.call_count, 1)

    def test_une_ecriture_refusee_n_est_pas_incertaine(self):
        refus = urllib.error.HTTPError("https://exemple.test", 403, "Forbidden", {}, None)
        with patch("urllib.request.urlopen", side_effect=refus) as appel:
            with self.assertRaisesRegex(MailcowAPIError, "HTTP 403"):
                self._client()._request("POST", "/add/alias", {"address": "a@b.test"})
        self.assertEqual(appel.call_count, 1)

    def test_chaque_appel_a_un_delai(self):
        with patch(
            "urllib.request.urlopen", return_value=FausseReponse('[{"type": "success"}]')
        ) as appel:
            self._client()._request("GET", "/get/domain/all", None)
        self.assertEqual(appel.call_args.kwargs["timeout"], 30)


@tagged("mailcow_admin", "post_install", "-at_install")
class TestCleDeLEnvironnement(TransactionCase):
    """La clé API vient de l'environnement (Vaultwarden), pas de la base."""

    def setUp(self):
        super().setUp()
        self.icp = self.env["ir.config_parameter"].sudo()
        self.icp.set_str("mailcow.base_url", "https://mail.example.com")
        self.icp.set_str("mailcow.api_key", "cle-en-base")
        self.icp.set_str("database.is_neutralized", "")

    def test_l_environnement_l_emporte_sur_la_base(self):
        with patch.dict("os.environ", {"MAILCOW_API_KEY": "cle-de-vault"}):
            self.assertEqual(MailcowClient(self.env).api_key, "cle-de-vault")
            reglages = self.env["res.config.settings"].create({})
            self.assertTrue(reglages.mailcow_api_key_from_env)

    def test_sans_variable_la_base_sert_de_repli(self):
        with patch.dict("os.environ", {"MAILCOW_API_KEY": ""}):
            self.assertEqual(MailcowClient(self.env).api_key, "cle-en-base")
            self.assertFalse(self.env["res.config.settings"].create({}).mailcow_api_key_from_env)

    def test_base_neutralisee_ignore_l_environnement(self):
        self.icp.set_str("database.is_neutralized", "True")
        self.icp.set_str("mailcow.api_key", "")
        with patch.dict("os.environ", {"MAILCOW_API_KEY": "cle-de-vault"}):
            client = MailcowClient(self.env)
            self.assertEqual(client.api_key, "")
            with self.assertRaisesRegex(MailcowAPIError, "pas configuré"):
                client._request("GET", "/get/domain/all")

    def test_la_cle_n_apparait_dans_aucune_erreur(self):
        refus = urllib.error.HTTPError("https://mail.example.com", 401, "Unauthorized", {}, None)
        with patch.dict("os.environ", {"MAILCOW_API_KEY": "cle-de-vault"}):
            with patch("urllib.request.urlopen", side_effect=refus):
                with self.assertRaises(MailcowAPIError) as erreur:
                    MailcowClient(self.env)._request("GET", "/get/domain/all")
        self.assertNotIn("cle-de-vault", str(erreur.exception))
