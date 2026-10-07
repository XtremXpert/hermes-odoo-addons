# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Tests de la configuration softphone pour le navigateur (P3.3).

Couvre la logique d'assemblage de la configuration que le softphone
SIP.js (intégré dans l'onglet Discuss) envoie **directement à Wazo**
(voie native, v3 — SIP-over-WSS sur un endpoint WebRTC) :

* l'AOR (nom d'endpoint, en-tête ``From``) — port séparé de
  l'identifiant d'authentification (extension) ; c'est la découverte
  critique P3.2 (endpoint généré Wazo confgen) ;
* l'URL WebSocket de Wazo (``wazo.ws_url``, repli dérivé de
  ``wazo.url``) — l'override relay de la v2 est **ignoré** ;
* le domaine SIP (PBX) ;
* la détection « prêt / non prêt » (état synchronisé + identifiants).
"""

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSoftphoneConfig(TransactionCase):
    def setUp(self):
        super().setUp()
        self.icp = self.env["ir.config_parameter"].sudo()
        # Ne laisse pas de paramètres en place.
        self.icp.search(
            [
                (
                    "key",
                    "in",
                    [
                        "wazo.url",
                        "wazo.ws_url",
                        "wazo.pbx_domain",
                        "wazo.softphone_ws_url",
                        "wazo.softphone_enabled",
                        "wazo.softphone_engine",
                    ],
                ),
            ]
        ).unlink()
        self.partner = self.env["res.partner"].create({"name": "Utilisateur Softphone"})
        self.user = self.env["res.users"].create(
            {
                "name": "Utilisateur Softphone",
                "login": "wazo_softphone_test",
                "partner_id": self.partner.id,
            }
        )

    def _synced_wizo(self, **overrides):
        values = {
            "name": "Utilisateur Softphone",
            "partner_id": self.partner.id,
            "extension": "1011",
            "wazo_state": "synced",
            "sip_username": "1011",
            "sip_password": "reg_secret_1011",
            # Nom d'endpoint généré par Wazo confgen (= l'AOR) :
            # volontairement différent de l'extension.
            "remote_endpoint_name": "m0kxsfvz",
        }
        values.update(overrides)
        return self.env["wazo.user"].create(values)

    # ------------------------------------------------------------------
    # AOR (nom d'endpoint)
    # ------------------------------------------------------------------

    def test_aor_uses_remote_endpoint_name(self):
        """L'AOR est le nom d'endpoint (différent de l'extension)."""
        wiz = self._synced_wizo()
        self.assertEqual(wiz._softphone_aor(), "m0kxsfvz")

    def test_aor_falls_back_to_extension(self):
        """Sans nom d'endpoint connu : l'extension (endpoint manuel)."""
        wiz = self._synced_wizo(remote_endpoint_name=False)
        self.assertEqual(wiz._softphone_aor(), "1011")

    # ------------------------------------------------------------------
    # URL WebSocket (voie native — l'override relay v2 est ignoré)
    # ------------------------------------------------------------------

    def test_ws_url_ignores_relay_override(self):
        """v3 : ``wazo.softphone_ws_url`` (relay B2BUA) est IGNORÉ.

        Ce paramètre servait à pointer le softphone sur le relay Sippy
        (v2). En v3 le navigateur parle directement à Wazo : l'URL est
        celle de l'endpoint WebRTC natif, et l'override relay ne doit
        plus avoir d'effet.
        """
        self.icp.set_str("wazo.softphone_ws_url", "wss://relay.bemade.org:9876")
        self.icp.set_str("wazo.ws_url", "wss://wazo.example/api/asterisk/ws")
        wiz = self._synced_wizo()
        self.assertEqual(wiz._softphone_ws_url(), "wss://wazo.example/api/asterisk/ws")

    def test_ws_url_uses_wazo_ws(self):
        """Le softphone se connecte à l'URL WebSocket de Wazo."""
        self.icp.set_str("wazo.ws_url", "wss://wazo.example/api/asterisk/ws")
        wiz = self._synced_wizo()
        self.assertEqual(wiz._softphone_ws_url(), "wss://wazo.example/api/asterisk/ws")

    def test_ws_url_derived_from_wazo_url(self):
        """Sans URL explicite : dérivée de l'URL Wazo (chemin Asterisk)."""
        self.icp.set_str("wazo.url", "https://wazo.example")
        wiz = self._synced_wizo()
        self.assertEqual(wiz._softphone_ws_url(), "wss://wazo.example/api/asterisk/ws")

    def test_ws_url_empty_when_unconfigured(self):
        """Aucune URL configurée : chaîne vide."""
        wiz = self._synced_wizo()
        self.assertEqual(wiz._softphone_ws_url(), "")

    # ------------------------------------------------------------------
    # Domaine SIP
    # ------------------------------------------------------------------

    def test_domain_uses_pbx_domain(self):
        self.icp.set_str("wazo.pbx_domain", "pbx.example.com")
        wiz = self._synced_wizo()
        self.assertEqual(wiz._softphone_domain(), "pbx.example.com")

    def test_domain_defaults_to_asterisk(self):
        wiz = self._synced_wizo()
        self.assertEqual(wiz._softphone_domain(), "asterisk")

    # ------------------------------------------------------------------
    # Disponibilité
    # ------------------------------------------------------------------

    def test_enabled_by_default(self):
        wiz = self._synced_wizo()
        self.assertTrue(wiz._softphone_enabled())

    def test_disabled_by_param(self):
        self.icp.set_bool("wazo.softphone_enabled", False)
        wiz = self._synced_wizo()
        self.assertFalse(wiz._softphone_enabled())

    # ------------------------------------------------------------------
    # Assemblage de la configuration
    # ------------------------------------------------------------------

    def test_config_empty_when_not_synced(self):
        """Non synchronisé : pas de configuration."""
        wiz = self.env["wazo.user"].create(
            {
                "name": "Non sync",
                "partner_id": self.partner.id,
                "extension": "1011",
                "wazo_state": "new",
            }
        )
        self.assertEqual(wiz.get_softphone_config(), {})

    def test_config_empty_without_sip(self):
        """Synchronisé mais sans identifiants SIP : pas de configuration."""
        wiz = self._synced_wizo(sip_username=False)
        self.assertEqual(wiz.get_softphone_config(), {})

    def test_config_empty_when_disabled(self):
        self.icp.set_bool("wazo.softphone_enabled", False)
        wiz = self._synced_wizo()
        self.assertEqual(wiz.get_softphone_config(), {})

    def test_config_assembles_full_dict(self):
        """Configuration complète (AOR ≠ auth_user, URL native de Wazo).

        Le paramètre relay ``wazo.softphone_ws_url`` est posé exprès :
        il doit être **sans effet** (contrat v3).
        """
        self.icp.set_str("wazo.softphone_ws_url", "wss://relay:9876")
        self.icp.set_str("wazo.ws_url", "wss://wazo.example/api/asterisk/ws")
        self.icp.set_str("wazo.pbx_domain", "asterisk")
        wiz = self._synced_wizo()
        cfg = wiz.get_softphone_config()
        self.assertEqual(
            cfg,
            {
                "enabled": True,
                "ws_url": "wss://wazo.example/api/asterisk/ws",
                "aor": "m0kxsfvz",  # nom d'endpoint (From)
                "auth_user": "1011",  # identifiant d'auth (extension)
                "auth_password": "reg_secret_1011",
                "domain": "asterisk",
                "display_name": "Utilisateur Softphone",
                "extension": "1011",
                "engine": "wazo_sdk",
            },
        )

    def test_config_aor_falls_back_to_extension(self):
        """AOR absent → repli sur l'extension (endpoint manuel)."""
        self.icp.set_str("wazo.ws_url", "wss://wazo.example/api/asterisk/ws")
        wiz = self._synced_wizo(remote_endpoint_name=False)
        cfg = wiz.get_softphone_config()
        self.assertEqual(cfg["aor"], "1011")
        self.assertEqual(cfg["auth_user"], "1011")

    # ------------------------------------------------------------------
    # Moteur SIP (P3.3f)
    # ------------------------------------------------------------------

    def test_engine_defaults_to_wazo_sdk(self):
        """Par défaut : le moteur du SDK officiel Wazo (décision P3.3f).

        Le moteur SIP.js écrit à la main ne câblait pas l'audio distant
        (il s'établissait muet) : le SDK, qui fournit l'attachement du
        média, est le moteur retenu.
        """
        wiz = self._synced_wizo()
        self.assertEqual(wiz._softphone_engine(), "wazo_sdk")

    def test_engine_from_param(self):
        """Le moteur reste sélectionnable par paramètre (repli SIP.js)."""
        self.icp.set_str("wazo.softphone_engine", "sipjs")
        wiz = self._synced_wizo()
        self.assertEqual(wiz._softphone_engine(), "sipjs")

    def test_engine_rejects_unknown_value(self):
        """Une valeur inconnue retombe sur le moteur retenu, jamais sur rien."""
        self.icp.set_str("wazo.softphone_engine", "moteur-imaginaire")
        wiz = self._synced_wizo()
        self.assertEqual(wiz._softphone_engine(), "wazo_sdk")

    def test_config_exposes_engine(self):
        """La configuration porte le moteur : c'est le service qui choisit."""
        self.icp.set_str("wazo.ws_url", "wss://wazo.example/api/asterisk/ws")
        self.icp.set_str("wazo.softphone_engine", "sipjs")
        wiz = self._synced_wizo()
        self.assertEqual(wiz.get_softphone_config()["engine"], "sipjs")
