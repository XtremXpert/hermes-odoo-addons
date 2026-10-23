# Part of the mailcow_tenant Odoo module. See LICENSE for details.
"""Le sort d'une notification Mailcow : elle doit atteindre l'utilisateur."""

import io
import json
from unittest.mock import patch

from odoo.addons.mailcow_tenant.services.mailcow_client import MailcowClient
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("mailcow_tenant", "post_install", "-at_install")
class TestNotificationMailcow(TransactionCase):
    """Une réponse Mailcow qui porte un message doit parvenir à l'utilisateur.

    Le piège que ce test ferme : publier sur un canal dont personne ne connaît
    le nom. Le code s'exécute, aucune erreur n'est levée, rien n'arrive — et
    l'utilisateur ne voit que les comptes rendus de synchronisation.

    Pourquoi ce test surveille l'appel et non la table du bus : ``bus.bus``
    n'est pas fiable depuis une transaction de test. Mesuré — ``_sendone``
    écrit bien une ligne, mais elle échappe à la lecture du test, si bien
    qu'une assertion sur la table échoue aussi bien quand la notification part
    au mauvais endroit que quand l'instrument est aveugle. On vérifie donc le
    contrat que la méthode doit respecter : la **destination** (la connexion de
    l'utilisateur, pas une chaîne libre) et le **type** que le client web sait
    afficher.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_str(
            "mailcow.base_url", "https://mail.example.com"
        )
        cls.env["ir.config_parameter"].sudo().set_str("mailcow.api_key", "test-api-key")

    def _reponse_portant(self, charge):
        """Une réponse HTTP factice portant la charge voulue."""
        flux = io.BytesIO(json.dumps(charge).encode("utf-8"))
        return type(
            "CM",
            (),
            {
                "__enter__": lambda soi: flux,
                "__exit__": lambda soi, *reste: False,
            },
        )()

    def test_un_message_en_liste_reste_lisible(self):
        """Mailcow renvoie parfois une cle de traduction, pas une phrase.

        Releve sur le serveur : /add/domain repond
        {"msg": ["domain_added", "test636.diverse-cite.com"]}. Coller cette
        liste telle quelle dans le bandeau affiche du JSON a l'utilisateur.
        """
        publies = []
        with patch.object(
            type(self.env["bus.bus"]), "_sendone", side_effect=lambda *a, **k: publies.append(a)
        ):
            MailcowClient(self.env)._notify(
                {
                    "type": "success",
                    "msg": ["domain_added", "test636.diverse-cite.com"],
                }
            )
        self.assertEqual(len(publies), 1, "la notification n'a pas ete publiee")
        message = publies[0][2]["message"]
        self.assertIsInstance(message, str, "le bandeau afficherait du JSON")
        self.assertIn("domain added", message)
        self.assertNotIn('["', message)

    def test_le_message_atteint_l_utilisateur(self):
        """La notification vise la connexion de l'utilisateur, pas un canal libre."""
        with (
            patch(
                "urllib.request.urlopen",
                return_value=self._reponse_portant([{"type": "success", "msg": "Domaine ajouté"}]),
            ),
            patch.object(type(self.env["bus.bus"]), "_sendone") as envoi,
        ):
            MailcowClient(self.env)._request("GET", "/get/domain/all")

        self.assertTrue(envoi.called, "aucune notification n'a été publiée")

        # Lecture défensive : un appel malformé (trop peu d'arguments) doit
        # échouer sur un message clair, pas sur une erreur de dépaquetage.
        arguments, nommes = envoi.call_args
        cible = arguments[0] if arguments else nommes.get("target")
        type_notification = arguments[1] if len(arguments) > 1 else nommes.get("notification_type")

        self.assertEqual(
            getattr(cible, "_name", None),
            "res.users",
            "la notification part sur %r au lieu de la connexion de l'utilisateur" % (cible,),
        )
        self.assertEqual(
            cible.id, self.env.user.id, "la notification ne vise pas l'utilisateur courant"
        )
        self.assertEqual(
            type_notification,
            "simple_notification",
            "le client web ne saura pas afficher %r" % (type_notification,),
        )
