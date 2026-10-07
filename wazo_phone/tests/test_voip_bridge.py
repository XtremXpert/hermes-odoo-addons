# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Tests du pont softphone (module « voip » d'Enterprise).

Le module « voip » n'est PAS installé dans la base de test : les
tests couvrent le comportement du pont en état « indisponible »
(no-ops) et vérifient la logique de propagation par mocks, sans
dépendre de ``voip.provider``.
"""

from odoo.addons.wazo_phone.services.wazo_client import WazoAPIError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


def _tuples(options):
    """Normalise une liste d'options JSON (listes) en tuples (hashables)."""
    return [tuple(o) for o in options]


@tagged("post_install", "-at_install")
class TestVoipBridge(TransactionCase):
    #: Option d'endpoint PJSIP activant les codecs WebRTC (opérateur booléen).
    WEBRTC_ENDPOINT_OPTION = ("allow", "opus,g722,alaw,ulaw,vp9,vp8,h264")

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Utilisateur Pont Test"})
        self.user = self.env["res.users"].create(
            {
                "name": "Utilisateur Pont Test",
                "login": "wazo_voip_bridge_test",
                "partner_id": self.partner.id,
            }
        )
        self.wizo = self.env["wazo.user"].create(
            {
                "name": "Utilisateur Pont Test",
                "partner_id": self.partner.id,
                "extension": "7000",
                "wazo_state": "synced",
                "sip_username": "sip_7000",
                "sip_password": "secret_7000",
            }
        )

    # ------------------------------------------------------------------
    # État « indisponible » (module voip absent)
    # ------------------------------------------------------------------

    def test_bridge_unavailable_without_voip_module(self):
        """Sans le module « voip », le pont est indisponible."""
        self.assertFalse(self.env["wazo.user"]._voip_available())

    def test_get_or_create_provider_empty_when_unavailable(self):
        """Le provider est vide (pas d'erreur) si le pont est indisponible."""
        provider = self.env["wazo.user"]._get_or_create_voip_provider()
        self.assertFalse(provider)

    def test_propagate_noop_when_unavailable(self):
        """La propagation est un no-op sans le module « voip »."""
        self.assertTrue(self.wizo._propagate_voip_credentials())

    def test_revoke_noop_when_unavailable(self):
        """La révocation est un no-op sans le module « voip », sans rien
        journaliser : l'identifiant softphone n'existe tout simplement pas."""
        with self.assertNoLogs("odoo.addons.wazo_phone.models.voip_bridge", "ERROR"):
            self.assertTrue(self.wizo._revoke_voip_credentials())

    # ------------------------------------------------------------------
    # Mapping des valeurs
    # ------------------------------------------------------------------

    def test_voip_user_values_full(self):
        """Mapping complet lorsque provider et identifiants existent."""
        provider = self.env.user  # substitut : un record avec un id
        values = self.wizo._voip_user_values(provider)
        self.assertEqual(
            values,
            {
                "voip_provider_id": provider.id,
                "voip_username": "sip_7000",
                "voip_secret": "secret_7000",
            },
        )

    def test_voip_user_values_without_provider(self):
        wiz = self.wizo
        values = wiz._voip_user_values(self.env["ir.model"].browse())
        self.assertEqual(values, {})

    def test_voip_user_values_without_sip(self):
        wiz = self.env["wazo.user"].create(
            {
                "name": "Sans identifiants SIP",
                "partner_id": self.partner.id,
                "extension": "7001",
            }
        )
        values = wiz._voip_user_values(self.env.user)
        self.assertEqual(values, {})

    def test_propagate_noop_without_odoo_user(self):
        """Aucun utilisateur Odoo lié au contact : aucune écriture."""
        calls = []
        self.patch(type(self.wizo), "_get_or_create_voip_provider", lambda self: self.env.user)
        self.patch(
            type(self.wizo),
            "_apply_voip_user_values",
            lambda self, user, values: calls.append(values),
        )
        partner = self.env["res.partner"].create({"name": "Sans utilisateur"})
        wiz = self.env["wazo.user"].create(
            {
                "name": "Sans utilisateur",
                "partner_id": partner.id,
                "extension": "7002",
                "sip_username": "sip_7002",
                "sip_password": "x",
            }
        )
        self.assertTrue(wiz._propagate_voip_credentials())
        self.assertEqual(calls, [])

    # ------------------------------------------------------------------
    # Propagation (mock du provider et de l'écriture)
    # ------------------------------------------------------------------

    def test_propagate_writes_values(self):
        """_propagate_voip_credentials applique le mapping à l'utilisateur."""
        calls = []
        self.patch(type(self.wizo), "_get_or_create_voip_provider", lambda self: self.env.user)
        self.patch(
            type(self.wizo),
            "_apply_voip_user_values",
            lambda self, user, values: calls.append((user, values)),
        )
        self.assertTrue(self.wizo._propagate_voip_credentials())
        self.assertEqual(len(calls), 1)
        user, values = calls[0]
        self.assertEqual(user, self.user)
        self.assertEqual(
            values,
            {
                "voip_provider_id": self.env.user.id,
                "voip_username": "sip_7000",
                "voip_secret": "secret_7000",
            },
        )

    def test_propagate_noop_without_credentials(self):
        """Aucun identifiant SIP : aucune écriture sur l'utilisateur."""
        calls = []
        self.patch(
            type(self.wizo),
            "_apply_voip_user_values",
            lambda self, user, values: calls.append(values),
        )
        # Provider indisponible (module absent) → recordset vide → no-op.
        self.assertTrue(self.wizo._propagate_voip_credentials())
        self.assertEqual(calls, [])

    def test_propagate_multiple_users(self):
        """Plusieurs utilisateurs Wazo : chaque utilisateur est écrit."""
        partner2 = self.env["res.partner"].create({"name": "Second Utilisateur"})
        user2 = self.env["res.users"].create(
            {
                "name": "Second Utilisateur",
                "login": "wazo_voip_bridge_test2",
                "partner_id": partner2.id,
            }
        )
        wiz2 = self.env["wazo.user"].create(
            {
                "name": "Second Utilisateur",
                "partner_id": partner2.id,
                "extension": "7003",
                "wazo_state": "synced",
                "sip_username": "sip_7003",
                "sip_password": "secret_7003",
            }
        )
        calls = []
        self.patch(type(self.wizo), "_get_or_create_voip_provider", lambda self: self.env.user)
        self.patch(
            type(self.wizo),
            "_apply_voip_user_values",
            lambda self, user, values: calls.append((user, values["voip_username"])),
        )
        self.assertTrue((self.wizo + wiz2)._propagate_voip_credentials())
        self.assertEqual(
            sorted(calls),
            [
                (self.user, "sip_7000"),
                (user2, "sip_7003"),
            ],
        )

    @mute_logger("odoo.addons.wazo_phone.models.voip_bridge")
    def test_propagate_swallows_apply_errors(self):
        """Une erreur d'écriture ne doit jamais casser la synchro."""

        def boom(self, user, values):
            raise RuntimeError("boom")

        self.patch(type(self.wizo), "_get_or_create_voip_provider", lambda self: self.env.user)
        self.patch(type(self.wizo), "_apply_voip_user_values", boom)
        # Ne doit pas lever.
        self.assertTrue(self.wizo._propagate_voip_credentials())

    # ------------------------------------------------------------------
    # Révocation
    # ------------------------------------------------------------------

    def test_revoke_when_username_matches(self):
        """Révocation lorsque l'identifiant utilisateur provient de Wazo."""
        calls = []
        self.patch(type(self.wizo), "_voip_username_of", lambda self, user: "sip_7000")
        self.patch(
            type(self.wizo),
            "_apply_voip_user_values",
            lambda self, user, values: calls.append((user, values)),
        )
        self.assertTrue(self.wizo._revoke_voip_credentials())
        self.assertEqual(
            calls,
            [
                (self.user, {"voip_username": False, "voip_secret": False}),
            ],
        )

    def test_revoke_when_username_differs(self):
        """Pas de révocation si l'identifiant en place ne vient pas de Wazo."""
        calls = []
        self.patch(type(self.wizo), "_voip_username_of", lambda self, user: "autre_identifiant")
        self.patch(
            type(self.wizo),
            "_apply_voip_user_values",
            lambda self, user, values: calls.append((user, values)),
        )
        self.assertTrue(self.wizo._revoke_voip_credentials())
        self.assertEqual(calls, [])

    # ------------------------------------------------------------------
    # Endpoint WebRTC (racine du softphone navigateur)
    # ------------------------------------------------------------------

    def test_endpoint_sip_payload_includes_webrtc_codec_option(self):
        """Le payload d'endpoint porte les codecs WebRTC (option 'allow')."""
        payload = self.env["wazo.user"]._build_endpoint_sip_payload(
            context="ctx-internal", extension="7000"
        )
        options = _tuples(payload.get("endpoint_sip", {}).get("endpoint_section_options", []))
        self.assertIn(
            self.WEBRTC_ENDPOINT_OPTION,
            options,
            "Le payload d'endpoint doit activer les codecs "
            "WebRTC pour qu'un navigateur puisse s'y inscrire.",
        )

    def test_endpoint_sip_payload_keeps_sip_auth_and_context(self):
        """Le payload conserve l'authentification SIP et le contexte."""
        payload = self.env["wazo.user"]._build_endpoint_sip_payload(
            context="ctx-internal", extension="7000"
        )
        ep = payload.get("endpoint_sip", {})
        self.assertIn(("username", "7000"), _tuples(ep.get("auth_section_options", [])))
        self.assertIn(("context", "ctx-internal"), _tuples(ep.get("endpoint_section_options", [])))

    # ------------------------------------------------------------------
    # Templates SIP du tenant (voie native v3 : endpoint WebRTC)
    # ------------------------------------------------------------------

    def test_endpoint_sip_payload_uses_tenant_templates(self):
        """Avec les templates du tenant, l'endpoint s'y réfère.

        Voie native (spec P3 v3) : les options WebRTC (``webrtc=yes``,
        codecs, transport ``wss``) viennent des templates ``global`` +
        ``webrtc`` du tenant. Le module ne doit PAS les réimplémenter en
        double — c'est la dérive garantie (la réplique locale avait
        d'ailleurs oublié ``webrtc=yes``).
        """
        payload = self.env["wazo.user"]._build_endpoint_sip_payload(
            context="ctx-internal",
            extension="7000",
            templates={"global": "uuid-global", "webrtc": "uuid-webrtc"},
        )
        endpoint = payload["endpoint_sip"]
        self.assertEqual(
            endpoint["templates"],
            [{"uuid": "uuid-global"}, {"uuid": "uuid-webrtc"}],
            "L'ordre compte : le template ``webrtc`` doit venir après "
            "``global`` pour le surcharger.",
        )
        options = _tuples(endpoint["endpoint_section_options"])
        self.assertNotIn(
            self.WEBRTC_ENDPOINT_OPTION,
            options,
            "Les options WebRTC venant du template, la réplique locale ne "
            "doit pas être ajoutée en double.",
        )
        # Le contexte, lui, n'est porté par aucun template : il reste
        # explicite sur l'endpoint.
        self.assertIn(("context", "ctx-internal"), options)
        self.assertIn(("username", "7000"), _tuples(endpoint["auth_section_options"]))

    def test_endpoint_sip_payload_falls_back_without_templates(self):
        """Sans template résolu : repli sur la réplique locale des options."""
        payload = self.env["wazo.user"]._build_endpoint_sip_payload(
            context="ctx-internal", extension="7000", templates={}
        )
        endpoint = payload["endpoint_sip"]
        self.assertNotIn("templates", endpoint)
        self.assertIn(self.WEBRTC_ENDPOINT_OPTION, _tuples(endpoint["endpoint_section_options"]))

    def test_get_sip_template_uuids_reads_tenant(self):
        """Les UUID de templates sont lus sur le tenant (global + webrtc)."""
        seen = {}

        class _FakeClient:
            tenant_id = "tenant-uuid"

            def conf(self, method, path, params=None, body=None):
                seen["call"] = (method, path)
                return {
                    "global_sip_template_uuid": "uuid-global",
                    "webrtc_sip_template_uuid": "uuid-webrtc",
                }

        uuids = self.env["wazo.user"]._get_sip_template_uuids(_FakeClient())
        self.assertEqual(uuids, {"global": "uuid-global", "webrtc": "uuid-webrtc"})
        self.assertEqual(seen["call"], ("GET", "/tenants/tenant-uuid"))

    def test_get_sip_template_uuids_is_defensive(self):
        """Sans tenant, en erreur API ou réponse inattendue → repli ({}):
        la synchronisation ne doit jamais casser pour une résolution de
        template (le payload retombe alors sur la réplique locale)."""

        class _NoTenant:
            tenant_id = False

            def conf(self, *args, **kwargs):
                raise AssertionError("aucun appel attendu sans tenant")

        class _Broken:
            tenant_id = "tenant-uuid"

            def conf(self, *args, **kwargs):
                raise WazoAPIError("HTTP 500. boom")

        class _Unexpected:
            tenant_id = "tenant-uuid"

            def conf(self, *args, **kwargs):
                return []

        for client in (_NoTenant(), _Broken(), _Unexpected()):
            self.assertEqual(
                self.env["wazo.user"]._get_sip_template_uuids(client),
                {},
                "La résolution doit échouer en douceur (repli).",
            )

    def test_ws_url_derived_from_wazo_url(self):
        """L'URL WebSocket SIP est dérivée de l'URL Wazo (chemin Asterisk)."""
        self.env["ir.config_parameter"].sudo().set_str(
            "wazo.url", "https://wazo-test.636.vezina.biz"
        )
        url = self.env["wazo.user"]._get_voip_ws_url()
        self.assertEqual(url, "wss://wazo-test.636.vezina.biz/api/asterisk/ws")

    def test_ws_url_keeps_explicit_override(self):
        """Une URL explicite (paramètre dédié) prend le pas sur la dérivée."""
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_str("wazo.url", "https://wazo-test.636.vezina.biz")
        icp.set_str("wazo.ws_url", "wss://autre.hote/api/asterisk/ws")
        url = self.env["wazo.user"]._get_voip_ws_url()
        self.assertEqual(url, "wss://autre.hote/api/asterisk/ws")
        icp.search([("key", "=", "wazo.ws_url")]).unlink()

    def test_ws_url_empty_when_not_configured(self):
        """Sans URL Wazo ni paramètre explicite : aucune URL WebSocket."""
        icp = self.env["ir.config_parameter"].sudo()
        icp.search([("key", "in", ("wazo.url", "wazo.ws_url"))]).unlink()
        self.assertEqual(self.env["wazo.user"]._get_voip_ws_url(), "")

    # ------------------------------------------------------------------
    # Filage des réglages
    # ------------------------------------------------------------------

    def test_settings_fields_wired(self):
        """Les champs du pont sont filés sur les bons paramètres."""
        settings = self.env["res.config.settings"]
        for fname, param in [
            ("wazo_softphone_enabled", "wazo.softphone_enabled"),
            ("wazo_ws_url", "wazo.ws_url"),
            ("wazo_pbx_domain", "wazo.pbx_domain"),
        ]:
            self.assertEqual(settings._fields[fname].config_parameter, param)
