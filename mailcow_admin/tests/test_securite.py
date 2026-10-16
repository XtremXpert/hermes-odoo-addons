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


@tagged("mailcow_admin", "post_install", "-at_install")
class TestDroitsParMethode(TransactionCase):
    """Le bouton masqué ne protège pas la méthode : chaque appel RPC est vérifié."""

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
