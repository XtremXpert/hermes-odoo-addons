# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Tests du flux de synchronisation utilisateur Wazo (confd + authd moqués).

Le flux complet (Wazo 26) est : extension, résolution des templates SIP du
tenant (global + webrtc, référencés par l'endpoint du softphone), ligne SIP
(``POST /lines``), utilisateur, association utilisateur/ligne, messagerie
vocale, association utilisateur/messagerie, puis le compte SIP
d'authentification via ``authd`` (``POST /api/auth/0.1/users``).
"""

from unittest.mock import patch

from odoo.addons.wazo_phone.services.wazo_client import WazoAPIError
from odoo.addons.wazo_phone.services.wazo_client import WazoClient
from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests import tagged


def _conf_side_effect(calls, fail_at=None):
    """Répond aux appels confd dans l'ordre du flux.

    ``calls`` : liste (méthode, path) dans l'ordre attendu.
    ``fail_at`` : index (0-based) de l'appel qui lève une erreur.
    """
    index = {"i": 0}

    def conf(method, path, params=None, body=None):
        i = index["i"]
        index["i"] += 1
        if fail_at is not None and i == fail_at:
            raise WazoAPIError("HTTP 500. boom")
        expected = calls[i] if i < len(calls) else None
        assert (method, path) == expected, "appel %d : attendu %r, reçu %r" % (
            i,
            expected,
            (method, path),
        )
        if path.startswith("/tenants/"):
            return {
                "global_sip_template_uuid": "uuid-global",
                "webrtc_sip_template_uuid": "uuid-webrtc",
            }
        if method == "GET":
            return []
        if path == "/extensions":
            return {"id": 10, "exten": "5550", "context": "default"}
        if path == "/lines":
            return {"id": 20}
        if path == "/users":
            assert body["firstname"] and body["lastname"]
            # L'API rend l'id **et** l'uuid : le premier sert aux URL, le
            # second aux associations (membres de groupe, par uuid).
            return {"id": "u-30-uuid", "uuid": "user-uuid-30"}
        if path == "/voicemails":
            return {"id": 50, "number": "5550"}
        return None

    return conf


def _auth_side_effect():
    """Répond aux appels authd (création du compte SIP, et lecture en
    secours en cas de 409 sur le re-sync)."""

    def auth(method, path, params=None, body=None):
        if (method, path) == ("POST", "/users"):
            assert body["username"] == "5550"
            assert body["password"]
            return {"uuid": "auth-uuid-1", "username": "5550"}
        if (method, path) == ("GET", "/users"):
            # Lecture du compte existant (reprise) : structure liste.
            return {"total": 1, "items": [{"uuid": "auth-uuid-1", "username": "5550"}]}
        raise AssertionError("appel authd inattendu : %s %s" % (method, path))

    return auth


FULL_CALLS = [
    ("GET", "/extensions"),
    # P4.2 : résolution du contexte pour lire les plages déclarées avant
    # toute écriture distante (le poste saisi doit être dans sa plage).
    ("GET", "/contexts"),
    ("POST", "/extensions"),
    ("GET", "/tenants/tenant-test-uuid"),
    ("POST", "/lines"),
    ("POST", "/users"),
    ("PUT", "/users/u-30-uuid/lines/20"),
    ("POST", "/voicemails"),
    ("PUT", "/users/u-30-uuid/voicemails/50"),
]


@tagged("wazo_phone", "post_install", "-at_install")
class TestWazoUserSync(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Contexte de test constant : le paramètre persistant de la base
        # (posé lors d'un sync live) ne doit pas contaminer l'assertion.
        cls.env["ir.config_parameter"].sudo().set_str("wazo.url", "https://wazo.example.com")
        cls.env["ir.config_parameter"].sudo().set_str("wazo.api_key", "test-api-token")
        cls.env["ir.config_parameter"].sudo().set_str("wazo.line_context", "default")
        cls.env["ir.config_parameter"].sudo().set_str("wazo.tenant_id", "tenant-test-uuid")

    def _create_wazo_user(self):
        partner = self.env["res.partner"].create({"name": "Alice Dupont", "phone": "5145550550"})
        return self.env["wazo.user"].create(
            {
                "name": "Alice Dupont",
                "partner_id": partner.id,
                "extension": "5550",
            }
        )

    def _patch_sync(self, calls, fail_at=None):
        """Patch confd + authd pour le flux de synchronisation."""
        conf_patch = patch.object(
            WazoClient, "conf", side_effect=_conf_side_effect(calls, fail_at=fail_at)
        )
        auth_patch = patch.object(WazoClient, "auth", side_effect=_auth_side_effect())
        return conf_patch, auth_patch

    def test_sync_creates_all_remote_resources_in_order(self):
        wazo_user = self._create_wazo_user()
        conf_patch, auth_patch = self._patch_sync(FULL_CALLS)
        with conf_patch as conf, auth_patch as auth:
            wazo_user.action_sync_wazo()
        self.assertEqual([c.args[:2] for c in conf.call_args_list], FULL_CALLS)
        # Le compte SIP authd est bien créé (username = le poste).
        self.assertEqual(auth.call_count, 1)
        self.assertEqual(
            auth.call_args.kwargs.get("body", auth.call_args[1].get("body")),
            {
                "username": "5550",
                "password": auth.call_args.kwargs.get("body", auth.call_args[1].get("body"))[
                    "password"
                ],
            },
        )
        wazo_user = self.env["wazo.user"].browse(wazo_user.id)
        self.assertEqual(wazo_user.wazo_state, "synced")
        self.assertEqual(wazo_user.remote_extension_id, 10)
        self.assertEqual(wazo_user.remote_line_id, 20)
        self.assertEqual(wazo_user.remote_user_id, "u-30-uuid")
        # L'uuid est conservé séparément : c'est lui que réclameront les
        # associations par utilisateur (membres d'un groupe d'appel, P4.3).
        self.assertEqual(wazo_user.remote_user_uuid, "user-uuid-30")
        self.assertEqual(wazo_user.sip_username, "5550")
        self.assertTrue(wazo_user.sip_password)
        # L'UUID du compte SIP authd est bien stocké (utilisé à la
        # suppression, car l'API authd se référence par UUID).
        self.assertEqual(wazo_user.remote_sip_id, "auth-uuid-1")

    def test_sync_endpoint_sip_references_webrtc_template(self):
        """L'endpoint créé référence les templates SIP du tenant.

        Voie native (spec P3 v3) : le navigateur s'inscrit sur un endpoint
        WebRTC. Ses options (``webrtc=yes``, codecs, transport ``wss``)
        viennent des templates ``global`` + ``webrtc`` du tenant — on ne
        réimplémente pas leurs valeurs dans le module (dérive garantie).
        """
        wazo_user = self._create_wazo_user()
        seen = {}

        def conf(method, path, params=None, body=None):
            if path.startswith("/tenants/"):
                return {
                    "global_sip_template_uuid": "uuid-global",
                    "webrtc_sip_template_uuid": "uuid-webrtc",
                }
            if method == "GET":
                return []
            if path == "/extensions":
                return {"id": 10, "exten": "5550", "context": "default"}
            if path == "/lines":
                seen["line_body"] = body
                return {"id": 20}
            if path == "/users":
                return {"id": "u-30-uuid"}
            if path == "/voicemails":
                return {"id": 50}
            return None

        with (
            patch.object(WazoClient, "conf", side_effect=conf),
            patch.object(WazoClient, "auth", side_effect=_auth_side_effect()),
        ):
            wazo_user.action_sync_wazo()
        endpoint = seen["line_body"]["endpoint_sip"]
        self.assertEqual(
            endpoint["templates"],
            [{"uuid": "uuid-global"}, {"uuid": "uuid-webrtc"}],
            "L'endpoint doit référencer le template global PUIS le "
            "template webrtc (le second surcharge le premier).",
        )

    def test_sync_stores_endpoint_name_when_response_carries_the_object(self):
        """La synchronisation enregistre le NOM de l'endpoint, pas l'objet.

        Mesuré en direct sur Wazo 26 : la réponse de ``POST /lines`` porte
        ``endpoint_sip`` sous forme d'**objet complet** (uuid, options,
        templates…), et non le nom. Or ``remote_endpoint_name`` est l'AOR du
        softphone (en-tête ``From``) : y écrire l'objet produit un en-tête
        invalide et un softphone muet, sans erreur visible côté serveur.
        """
        wazo_user = self._create_wazo_user()

        def conf(method, path, params=None, body=None):
            if path.startswith("/tenants/"):
                return {
                    "global_sip_template_uuid": "uuid-global",
                    "webrtc_sip_template_uuid": "uuid-webrtc",
                }
            if method == "GET":
                return []
            if path == "/extensions":
                return {"id": 10, "exten": "5550", "context": "default"}
            if path == "/lines":
                return {
                    "id": 20,
                    "endpoint_sip": {
                        "uuid": "ep-uuid",
                        "name": "bvkixf7o",
                        "label": None,
                        "templates": [{"uuid": "uuid-global", "label": "global"}],
                        "endpoint_section_options": [["context", "default"]],
                    },
                }
            if path == "/users":
                return {"id": "u-30-uuid"}
            if path == "/voicemails":
                return {"id": 50}
            return None

        with (
            patch.object(WazoClient, "conf", side_effect=conf),
            patch.object(WazoClient, "auth", side_effect=_auth_side_effect()),
        ):
            wazo_user.action_sync_wazo()
        self.assertEqual(
            wazo_user.remote_endpoint_name,
            "bvkixf7o",
            "L'AOR doit être le nom de l'endpoint, jamais l'objet renvoyé "
            "par l'API (l'en-tête From du softphone serait invalide).",
        )

    def test_sync_stores_endpoint_name_when_response_carries_the_name(self):
        """Une réponse qui porte directement le nom reste acceptée."""
        wazo_user = self._create_wazo_user()

        def conf(method, path, params=None, body=None):
            if path.startswith("/tenants/"):
                return {
                    "global_sip_template_uuid": "uuid-global",
                    "webrtc_sip_template_uuid": "uuid-webrtc",
                }
            if method == "GET":
                return []
            if path == "/extensions":
                return {"id": 10, "exten": "5550", "context": "default"}
            if path == "/lines":
                return {"id": 20, "endpoint_sip": "zo5qsdg5"}
            if path == "/users":
                return {"id": "u-30-uuid"}
            if path == "/voicemails":
                return {"id": 50}
            return None

        with (
            patch.object(WazoClient, "conf", side_effect=conf),
            patch.object(WazoClient, "auth", side_effect=_auth_side_effect()),
        ):
            wazo_user.action_sync_wazo()
        self.assertEqual(wazo_user.remote_endpoint_name, "zo5qsdg5")

    def test_sync_reuses_existing_extension(self):
        wazo_user = self._create_wazo_user()
        # Reprise : le poste existe déjà côté Wazo à cause d'une tentative
        # précédente — l'état 'error' est ce qui l'autorise (P4.2b). Dans
        # l'état 'nouveau', un poste déjà présent est au contraire refusé :
        # il ne peut pas venir de cette fiche, qui n'a jamais été tentée.
        wazo_user.write({"wazo_state": "error"})
        # Le GET renvoie le poste existant (id 99) → POST /extensions évité,
        # et la ligne porte bien le poste 99 dans son body.
        expected = [
            ("GET", "/extensions"),
            ("GET", "/tenants/tenant-test-uuid"),
            ("POST", "/lines"),
            ("POST", "/users"),
            ("PUT", "/users/u-30-uuid/lines/20"),
            ("POST", "/voicemails"),
            ("PUT", "/users/u-30-uuid/voicemails/50"),
        ]
        index = {"i": 0}

        def conf(method, path, params=None, body=None):
            i = index["i"]
            index["i"] += 1
            assert (method, path) == expected[i], "appel %d : attendu %r, reçu %r" % (
                i,
                expected[i],
                (method, path),
            )
            if path.startswith("/tenants/"):
                return {
                    "global_sip_template_uuid": "uuid-global",
                    "webrtc_sip_template_uuid": "uuid-webrtc",
                }
            if method == "GET":
                return [{"id": 99, "exten": "5550", "context": "default"}]
            if path == "/lines":
                # La ligne doit cibler le poste existant (numéro 5550).
                self.assertEqual(body["extensions"], [{"exten": "5550"}])
                return {"id": 20}
            if path == "/users":
                return {"id": "u-30-uuid"}
            if path == "/voicemails":
                return {"id": 50}
            return None

        with (
            patch.object(WazoClient, "conf", side_effect=conf),
            patch.object(WazoClient, "auth", side_effect=_auth_side_effect()),
        ):
            wazo_user.action_sync_wazo()
        wazo_user = self.env["wazo.user"].browse(wazo_user.id)
        self.assertEqual(wazo_user.remote_extension_id, 99)
        self.assertEqual(wazo_user.wazo_state, "synced")

    def test_sync_line_body_carries_extension_and_auth(self):
        wazo_user = self._create_wazo_user()
        seen = {}

        def conf(method, path, params=None, body=None):
            i = seen.setdefault("i", 0)
            seen["i"] = i + 1
            if method == "GET":
                return []
            if path == "/extensions":
                return {"id": 10, "exten": "5550", "context": "default"}
            if path == "/lines":
                seen["line_body"] = body
                return {"id": 20}
            if path == "/users":
                return {"id": "u-30-uuid"}
            if path == "/voicemails":
                return {"id": 50}
            return None

        with (
            patch.object(WazoClient, "conf", side_effect=conf),
            patch.object(WazoClient, "auth", side_effect=_auth_side_effect()),
        ):
            wazo_user.action_sync_wazo()
        body = seen["line_body"]
        # Le body de la ligne porte bien le contexte, le poste et
        # l'endpoint SIP avec le nom d'utilisateur d'authentification.
        self.assertEqual(body["context"], "default")
        self.assertEqual(body["extensions"], [{"exten": "5550"}])
        self.assertEqual(body["endpoint_sip"]["auth_section_options"], [["username", "5550"]])

    def test_sync_failure_marks_error_and_keeps_ids_unset(self):
        wazo_user = self._create_wazo_user()
        # Échec à l'étape 3 (création de l'utilisateur) : l'échec est
        # consigné sur la ligne sans remontée d'exception, pour que l'état
        # d'erreur survive au rollback transactionnel.
        conf_patch, auth_patch = self._patch_sync(FULL_CALLS, fail_at=5)
        with conf_patch, auth_patch:
            result = wazo_user.action_sync_wazo()
        self.assertFalse(result)
        wazo_user = self.env["wazo.user"].browse(wazo_user.id)
        self.assertEqual(wazo_user.wazo_state, "error")
        self.assertIn("boom", wazo_user.error_message)
        self.assertFalse(wazo_user.remote_user_id)

    def test_extension_is_required(self):
        wazo_user = self.env["wazo.user"].create({"name": "Sans poste", "extension": False})
        with self.assertRaises(UserError):
            wazo_user.action_sync_wazo()

    def test_double_sync_is_refused(self):
        wazo_user = self._create_wazo_user()
        conf_patch, auth_patch = self._patch_sync(FULL_CALLS)
        with conf_patch, auth_patch:
            wazo_user.action_sync_wazo()
        with self.assertRaises(UserError):
            wazo_user.action_sync_wazo()

    def test_delete_wazo_removes_resources_in_safe_order(self):
        wazo_user = self._create_wazo_user()
        conf_patch, auth_patch = self._patch_sync(FULL_CALLS)
        with conf_patch, auth_patch:
            wazo_user.action_sync_wazo()
        # Wazo 26 : la ligne est d'abord supprimée en récursif (retrait de
        # l'endpoint SIP, des extensions et de l'association utilisateur),
        # puis la messagerie vocale est dissociée de l'utilisateur et
        # supprimée, ensuite l'utilisateur, l'extension et le compte SIP
        # d'authentification (authd).
        delete_calls = [
            ("DELETE", "/lines/20?recursive=true"),
            ("DELETE", "/users/u-30-uuid/voicemails"),
            ("GET", "/voicemails"),
            ("DELETE", "/voicemails/50"),
            ("DELETE", "/users/u-30-uuid"),
            ("DELETE", "/extensions/10"),
        ]

        def _conf_side_effect(method, path, params=None, body=None):
            if method == "GET" and path == "/voicemails":
                # La messagerie vocale du poste (numéro 5550) existe.
                return {"total": 1, "items": [{"id": 50, "number": "5550", "context": "default"}]}
            if (method, path) not in delete_calls:
                raise AssertionError("appel inattendu : %s %s" % (method, path))
            return {}

        auth_delete = [("DELETE", "/users/auth-uuid-1")]

        def _auth_delete_effect(method, path, params=None, body=None):
            assert (method, path) in auth_delete, (method, path)
            return {"uuid": "auth-uuid-1", "username": "5550"}

        with (
            patch.object(WazoClient, "conf", side_effect=_conf_side_effect) as conf,
            patch.object(WazoClient, "auth", side_effect=_auth_delete_effect) as auth,
        ):
            wazo_user.action_delete_wazo()
        # L'ordre des appels conf est sûr (voicemail, user, ligne, extension).
        self.assertEqual([c.args[:2] for c in conf.call_args_list], delete_calls)
        self.assertEqual([c.args[:2] for c in auth.call_args_list], auth_delete)
        wazo_user = self.env["wazo.user"].browse(wazo_user.id)
        self.assertEqual(wazo_user.wazo_state, "new")
        self.assertFalse(wazo_user.remote_user_id)
        self.assertFalse(wazo_user.sip_password)
        self.assertFalse(wazo_user.remote_sip_id)

    def test_retry_sync_after_error(self):
        wazo_user = self._create_wazo_user()
        conf_patch, auth_patch = self._patch_sync(FULL_CALLS, fail_at=5)
        with conf_patch, auth_patch:
            wazo_user.action_sync_wazo()
        wazo_user = self.env["wazo.user"].browse(wazo_user.id)
        self.assertEqual(wazo_user.wazo_state, "error")
        # Extension déjà créée côté Wazo (id 10) : le flux la réutilise et
        # crée une nouvelle ligne (21) pour l'utilisateur (31) et la
        # messagerie (51).
        expected = [
            ("GET", "/extensions"),
            ("GET", "/tenants/tenant-test-uuid"),
            ("POST", "/lines"),
            ("POST", "/users"),
            ("PUT", "/users/31/lines/21"),
            ("POST", "/voicemails"),
            ("PUT", "/users/31/voicemails/51"),
        ]
        index = {"i": 0}

        def conf(method, path, params=None, body=None):
            i = index["i"]
            index["i"] += 1
            assert (method, path) == expected[i]
            if path.startswith("/tenants/"):
                return {
                    "global_sip_template_uuid": "uuid-global",
                    "webrtc_sip_template_uuid": "uuid-webrtc",
                }
            if method == "GET":
                return [{"id": 10, "exten": "5550", "context": "default"}]
            if path == "/lines":
                return {"id": 21}
            if path == "/users":
                return {"id": 31}
            if path == "/voicemails":
                return {"id": 51}
            return None

        with (
            patch.object(WazoClient, "conf", side_effect=conf),
            patch.object(WazoClient, "auth", side_effect=_auth_side_effect()),
        ):
            wazo_user.action_retry_sync()
        wazo_user = self.env["wazo.user"].browse(wazo_user.id)
        self.assertEqual(wazo_user.wazo_state, "synced")
        self.assertFalse(wazo_user.error_message)
