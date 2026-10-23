# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Tests de validation du poste utilisateur (P4.2).

Décision : le poste reste **saisi à la main** — aucune attribution
automatique — mais il est **refusé** s'il sort de la plage de son type, s'il
appartient à la plage d'un autre type, ou s'il est déjà attribué.

Les plages viennent du PBX (`GET /contexts/{id}`, toutes déclarées d'un coup)
et la disponibilité de `GET /contexts/{id}/ranges/user?availability=available`.
On ne recalcule jamais la disponibilité : le PBX considère toute extension
existante comme prise, même non attribuée.

Les relations d'une extension (`group`, `queue`, `lines`…) viennent de la
définition `Extension` de l'api.yml installé (`ExtensionRelationGroup`,
`ExtensionRelationLines`, …) : un poste rattaché à un groupe n'est donc pas
confondu avec une reprise de synchronisation.

Contrat retenu quand l'extension existe déjà côté Wazo : rattachée à un
**groupe / file / conférence / SVI**, c'est un refus ; rattachée à une **ligne**
ou à rien, c'est une **reprise** (le flux réutilise le poste, comportement
idempotent existant).
"""

from unittest.mock import patch

from odoo.addons.wazo_tenant.services.wazo_client import WazoAPIError
from odoo.addons.wazo_tenant.services.wazo_client import WazoClient
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase
from odoo.tests import tagged
from odoo.tools import mute_logger

CONTEXTE = "ctx-test-internal-dad46d8d-02df-4cf9-b92c-2f3bc736f039"

# Plages réellement déclarées sur le tenant `test` (relevées en direct).
DECLAREES = {
    "user_ranges": [{"start": "1000", "end": "1999"}],
    "group_ranges": [{"start": "2000", "end": "2099"}],
    "queue_ranges": [],
    "conference_room_ranges": [],
    "incall_ranges": [],
}

# Numéros libres du type `user` : 1001-1005 et 1011 sont occupés.
LIBRES_USER = [
    {"start": "1000", "end": "1000"},
    {"start": "1006", "end": "1010"},
    {"start": "1012", "end": "1999"},
]

# Numéros libres du type `group` : 2000 est pris par le groupe, 2001 par une
# extension orpheline (le PBX compte toute extension existante comme prise).
LIBRES_GROUP = [{"start": "2002", "end": "2099"}]

#: Une ligne Wazo telle que confd la rend, propriétaire compris. C'est
#: ``users`` qui porte l'**uuid** que réclament les associations par
#: utilisateur (membres d'un groupe d'appel).
LIGNE_WAZO = {
    "id": 12,
    "exten": "1005",
    "users": [{"uuid": "user-uuid-live", "firstname": "Odoo", "lastname": "Live Test"}],
}

#: Valeur par défaut de ``contextes`` dans le routeur : le contexte de test.
AUTO_CONTEXTES = "auto"


class WazoValidationTestBase(TransactionCase):
    """Base : confd simulé par **routage**, et non par séquence."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env["ir.config_parameter"].sudo()
        icp.set_str("wazo.url", "https://wazo.example.com")
        icp.set_str("wazo.api_key", "test-api-token")
        icp.set_str("wazo.tenant_id", "tenant-test-uuid")
        icp.set_str("wazo.line_context", CONTEXTE)

    def _create_user(self, extension):
        return self.env["wazo.user"].create({"name": "Alice Dupont", "extension": extension})

    def _router(
        self,
        appels,
        declared=None,
        libres=None,
        extensions=None,
        contexts_error=False,
        contextes=AUTO_CONTEXTES,
        users=None,
        libres_group=None,
        lignes=None,
        ligne=None,
        erreur_sur=None,
    ):
        """Faux confd, routé par (méthode, chemin)."""
        declared = DECLAREES if declared is None else declared
        libres = LIBRES_USER if libres is None else libres
        libres_group = LIBRES_GROUP if libres_group is None else libres_group
        extensions = list(extensions or [])
        users = list(users or [])
        lignes = [{"id": 12, "exten": "1005"}] if lignes is None else lignes
        ligne = LIGNE_WAZO if ligne is None else ligne

        def conf(method, path, params=None, body=None):
            appels.append((method, path))
            if erreur_sur and (method, path) == tuple(erreur_sur):
                # Panne simulée au milieu d'une séquence : sert à vérifier
                # qu'un échec partiel laisse des traces exploitables.
                raise WazoAPIError(
                    "Erreur de l'API Wazo (%s %s) : HTTP 400. Panne simulée." % (method, path)
                )
            champs = body or {}
            if path == "/extensions" and method == "GET":
                return {"total": len(extensions), "items": extensions}
            if path.startswith("/extensions/"):
                return None
            if path == "/lines" and method == "GET":
                return {"total": len(lignes), "items": lignes}
            if path.startswith("/lines/"):
                # Le propriétaire de la ligne : ``users`` porte l'uuid.
                return ligne
            if path == "/users" and method == "GET":
                return {"total": len(users), "items": users}
            if path == "/contexts":
                if contexts_error:
                    raise WazoAPIError("HTTP 500. plages illisibles")
                if contextes != AUTO_CONTEXTES:
                    return contextes
                return {"total": 1, "items": [{"id": 1, "name": CONTEXTE}]}
            if path == "/contexts/1":
                return dict({"id": 1, "name": CONTEXTE}, **declared)
            if path.startswith("/contexts/1/ranges/"):
                type_ = path.rsplit("/", 1)[-1]
                plages = libres_group if type_ == "group" else libres
                return {"total": len(plages or []), "items": list(plages or [])}
            if path.startswith("/tenants/"):
                return {
                    "global_sip_template_uuid": "uuid-global",
                    "webrtc_sip_template_uuid": "uuid-webrtc",
                }
            if path == "/extensions" and method == "POST":
                return {"id": 10, "exten": champs.get("exten")}
            if path == "/lines":
                return {"id": 20, "endpoint_sip": "ep-1"}
            if path == "/users" and method == "POST":
                return {"id": "u-30-uuid"}
            if path == "/voicemails":
                return {"id": 50}
            if path == "/groups" and method == "POST":
                return {"id": 3, "uuid": "grp-uuid-3", "name": "grp-test"}
            if path.startswith("/groups/"):
                # Associations (extension, membres) : 204 sans corps.
                return None
            if path.startswith("/users/"):
                return {}
            raise AssertionError("appel confd inattendu : %s %s" % (method, path))

        return conf

    @staticmethod
    def _auth():
        def auth(method, path, params=None, body=None):
            return {"uuid": "auth-uuid-1", "username": (body or {}).get("username")}

        return auth

    def _sync(self, wazo_user, **router_kwargs):
        """Lance la synchro contre le faux confd ; rend (appels, résultat)."""
        appels = []
        conf = self._router(appels, **router_kwargs)
        with (
            patch.object(WazoClient, "conf", side_effect=conf),
            patch.object(WazoClient, "auth", side_effect=self._auth()),
        ):
            resultat = wazo_user.action_sync_wazo()
        return appels, resultat

    def _expect_refusal(self, wazo_user, **router_kwargs):
        """Lance la synchro en attendant un refus ; rend (exception, appels).

        Le client **doit** être simulé : sans PBX, le contrôle ne peut rien
        vérifier et laisse passer (règle assumée : on n'invente ni refus ni
        autorisation quand les plages sont illisibles).
        """
        appels = []
        conf = self._router(appels, **router_kwargs)
        with (
            patch.object(WazoClient, "conf", side_effect=conf),
            patch.object(WazoClient, "auth", side_effect=self._auth()),
        ):
            with self.assertRaises(UserError) as ctx:
                wazo_user.action_sync_wazo()
        return ctx, appels


@tagged("wazo_tenant", "post_install", "-at_install")
class TestExtensionLocalRules(WazoValidationTestBase):
    """Règles vérifiables sans le PBX."""

    def test_extension_must_be_digits(self):
        with self.assertRaises(ValidationError):
            self._create_user("10a1")

    def test_extension_must_not_contain_separators(self):
        with self.assertRaises(ValidationError):
            self._create_user("100-1")

    def test_empty_extension_is_allowed(self):
        """Le poste est facultatif : c'est la synchro qui l'exige."""
        wazo_user = self._create_user(False)
        self.assertFalse(wazo_user.extension)

    def test_extension_must_be_unique_locally(self):
        """Deux enregistrements Odoo ne visent jamais le même poste."""
        self._create_user("1001")
        with self.assertRaises(ValidationError):
            self._create_user("1001")

    def test_extension_can_be_written_again_on_itself(self):
        """Réécrire la même valeur n'est pas un doublon."""
        wazo_user = self._create_user("1001")
        wazo_user.extension = "1001"  # ne lève pas


@tagged("wazo_tenant", "post_install", "-at_install")
class TestExtensionRangeRules(WazoValidationTestBase):
    """Règles de plage, vérifiées au moment de la synchronisation."""

    def test_extension_outside_any_declared_range_is_refused(self):
        wazo_user = self._create_user("5101")
        ctx, _ = self._expect_refusal(wazo_user)
        self.assertIn("plage", str(ctx.exception).lower())

    def test_extension_reserved_for_another_type_is_refused(self):
        """2005 est libre, mais dans la plage déclarée des groupes."""
        wazo_user = self._create_user("2005")
        ctx, _ = self._expect_refusal(wazo_user)
        self.assertIn("groupe", str(ctx.exception).lower())

    def test_extension_already_attached_to_a_group_is_refused(self):
        """Rattachée à un groupe, elle est refusée même hors de toute plage."""
        wazo_user = self._create_user("3000")
        ctx, _ = self._expect_refusal(
            wazo_user,
            extensions=[
                {
                    "id": 7,
                    "exten": "3000",
                    "context": CONTEXTE,
                    "group": {"uuid": "g-1", "name": "Groupe Ventes"},
                }
            ],
        )
        self.assertIn("groupe", str(ctx.exception).lower())

    def test_extension_in_range_but_taken_is_refused(self):
        """1001 est dans la plage des postes, mais indisponible."""
        wazo_user = self._create_user("1001")
        ctx, _ = self._expect_refusal(wazo_user)
        self.assertIn("attribu", str(ctx.exception).lower())

    def test_available_extension_is_accepted(self):
        """1000 est dans la plage et libre : la synchro aboutit."""
        wazo_user = self._create_user("1000")
        appels, resultat = self._sync(wazo_user)
        self.assertTrue(resultat)
        self.assertIn(("POST", "/extensions"), appels)
        self.assertEqual(self.env["wazo.user"].browse(wazo_user.id).wazo_state, "synced")

    def test_refusal_happens_before_any_remote_write(self):
        """Un refus ne doit rien créer côté Wazo."""
        wazo_user = self._create_user("5101")
        appels = []
        conf = self._router(appels)
        with (
            patch.object(WazoClient, "conf", side_effect=conf),
            patch.object(WazoClient, "auth", side_effect=self._auth()),
        ):
            with self.assertRaises(UserError):
                wazo_user.action_sync_wazo()
        self.assertEqual([a for a in appels if a[0] != "GET"], [])
        self.assertFalse(self.env["wazo.user"].browse(wazo_user.id).remote_user_id)

    def test_context_without_declared_ranges_skips_the_check(self):
        """Aucune plage déclarée : il n'y a pas de règle à faire respecter."""
        wazo_user = self._create_user("5101")
        _, resultat = self._sync(wazo_user, declared={})
        self.assertTrue(resultat)

    def test_extension_in_service_is_refused(self):
        """Le poste d'un utilisateur déjà en service n'est pas repris.

        Cas réel : 1011 appartient à « PoC Multi PoC » sur le PBX de test.
        """
        wazo_user = self._create_user("1011")
        ctx, appels = self._expect_refusal(
            wazo_user,
            extensions=[
                {
                    "id": 22,
                    "exten": "1011",
                    "context": CONTEXTE,
                    "lines": [{"id": 22, "name": "m0kxsfvz"}],
                }
            ],
            users=[{"id": 14, "firstname": "PoC Multi", "lastname": "PoC", "lines": [{"id": 22}]}],
        )
        message = str(ctx.exception).lower()
        self.assertIn("service", message)
        self.assertIn("poc multi poc", message)
        # Un refus ne crée rien : aucune écriture n'est émise.
        self.assertEqual([a for a in appels if a[0] != "GET"], [])

    def test_extension_present_without_line_is_refused(self):
        """Ressource résiduelle : présente côté Wazo, rattachée à rien.

        Cas réel : 5101, orpheline du PoC, hors de toute plage.
        """
        wazo_user = self._create_user("5101")
        ctx, _ = self._expect_refusal(
            wazo_user, extensions=[{"id": 5, "exten": "5101", "context": CONTEXTE}]
        )
        self.assertIn("résiduel", str(ctx.exception).lower())

    def test_extension_is_resumed_after_a_failure(self):
        """Reprise légitime : seulement après un échec constaté.

        Dans l'état « nouveau », aucune tentative n'a eu lieu : ce qui existe
        déjà côté Wazo ne peut pas venir de cette fiche.
        """
        wazo_user = self._create_user("5550")
        wazo_user.write({"wazo_state": "error"})
        appels, resultat = self._sync(
            wazo_user,
            extensions=[
                {
                    "id": 99,
                    "exten": "5550",
                    "context": CONTEXTE,
                    "lines": [{"id": 7, "name": "webrtc5550"}],
                }
            ],
        )
        self.assertTrue(resultat)
        self.assertNotIn(("GET", "/contexts"), appels)
        self.assertNotIn(("GET", "/users"), appels)
        self.assertEqual(self.env["wazo.user"].browse(wazo_user.id).remote_extension_id, 99)

    @mute_logger("odoo.addons.wazo_tenant.models.wazo_extension_mixin")
    def test_unreadable_ranges_do_not_block_the_sync(self):
        """PBX muet sur les plages : on n'invente ni refus ni autorisation."""
        wazo_user = self._create_user("1000")
        _, resultat = self._sync(wazo_user, contexts_error=True)
        self.assertTrue(resultat)

    def test_unknown_context_skips_the_check(self):
        """Contexte introuvable côté Wazo : aucune plage connue, on laisse."""
        wazo_user = self._create_user("5101")
        _, resultat = self._sync(wazo_user, contextes={"total": 0, "items": []})
        self.assertTrue(resultat)
