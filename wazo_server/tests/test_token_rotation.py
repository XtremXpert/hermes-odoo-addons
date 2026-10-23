# Part of the wazo_server Odoo module. See LICENSE for details.
"""Renouveler le jeton d'un tenant vivant (P7).

Le jeton est le secret qu'on remet au client. Le jour où son Odoo fuite —
sauvegarde, poste de travail, employé qui part —, l'exploitant doit pouvoir le
remplacer **sans détruire le tenant** : la suppression, elle, est refusée tant
que le tenant porte des postes, et emporterait le client avec elle.

La rotation fabrique donc un jeton neuf (``POST /token`` en Basic, avec les
identifiants d'administrateur déjà conservés sur la fiche) puis **révoque
l'ancien** (``DELETE /token/{jeton}``, route ouverte à qui connaît le jeton).

L'ordre compte : **émettre d'abord, révoquer ensuite**. Une révocation ratée
laisse alors deux jetons vivants — réparable, l'ancien mourant à son
expiration —, au lieu d'un client dont le jeton vient d'être tué avant que
l'Odoo ait le neuf.
"""

from unittest.mock import patch

from odoo.addons.wazo_tenant.services.wazo_client import WazoAPIError
from odoo.addons.wazo_tenant.services.wazo_client import WazoClient
from odoo.exceptions import AccessError
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .test_tenant_provisioning import WazoServerTestBase

TENANT = "e813ecfd-386d-4b0a-b45f-d9b0ec8d3a69"
ANCIEN = "ancien-jeton-du-client"
NOUVEAU = "jeton-renouvele-0001"
EXPIRATION = "2036-09-24T15:00:00.000000"
DIX_ANS = 315360000


@tagged("wazo_server", "post_install", "-at_install")
class TestTokenRotation(WazoServerTestBase):
    """Le jeton d'un tenant se remplace sans toucher au tenant."""

    def _tenant_cree(self, **valeurs):
        """Un tenant déjà créé sur Wazo : tout ce qu'il faut pour fabriquer un jeton."""
        valeurs.setdefault("name", "Client Alpha")
        valeurs.setdefault("slug", "alpha")
        valeurs.setdefault("state", "created")
        valeurs.setdefault("remote_uuid", TENANT)
        valeurs.setdefault("remote_context_name", "ctx-alpha-internal-0001")
        valeurs.setdefault("admin_username", "odoo_admin")
        valeurs.setdefault("admin_password", "mot-de-passe-admin")
        valeurs.setdefault("api_token", ANCIEN)
        valeurs.setdefault("token_expires_at", "2027-01-01 00:00:00")
        return self.env["wazo.server.tenant"].create(valeurs)

    def _faux_pbx(self, revocation_ratee=False):
        """Faux Wazo ne servant que le jeton : rien d'autre n'est attendu ici.

        Tout appel inattendu échoue avec le chemin, pour qu'un excès de zèle se
        voie au lieu de passer pour du silence.
        """
        appels = []

        def repondre(client, service, method, path, params=None, body=None, basic=None):
            appels.append((service, method, path, body or {}, client.tenant_id, basic))
            if service != "auth":
                raise WazoAPIError("Appel inattendu : %s %s" % (method, path))
            if method == "POST" and path == "/token":
                # Forme **brute** de la réponse : ``token()`` déplie ``data``.
                return {"data": {"token": NOUVEAU, "expires_at": EXPIRATION, "acl": ["confd.#"]}}
            if method == "DELETE" and path.startswith("/token/"):
                if revocation_ratee:
                    raise WazoAPIError("Erreur de l'API Wazo (DELETE %s) : HTTP 500." % path)
                return {"message": "Token revoked"}
            raise WazoAPIError("Appel inattendu : %s %s" % (method, path))

        return appels, repondre

    def _pose_patch(self, repondre):
        return patch.object(WazoClient, "_request", autospec=True, side_effect=repondre)

    def _tourne(self, tenant, **options):
        appels, repondre = self._faux_pbx(**options)
        with self._pose_patch(repondre):
            tenant.action_rotate_token()
        return appels

    # ------------------------------------------------------------------
    # Le jeton est remplacé, et l'ancien est tué
    # ------------------------------------------------------------------

    def test_rotation_replaces_the_token(self):
        tenant = self._tenant_cree()
        self._tourne(tenant)
        self.assertEqual(tenant.api_token, NOUVEAU)
        self.assertNotEqual(tenant.api_token, ANCIEN)
        self.assertTrue(tenant.token_rotated_at)

    def test_rotation_asks_for_a_ten_year_token(self):
        """Un jeton d'intégration ne doit pas expirer comme une session."""
        tenant = self._tenant_cree()
        appels = self._tourne(tenant)
        creations = [a for a in appels if a[1] == "POST" and a[2] == "/token"]
        self.assertEqual(len(creations), 1)
        self.assertEqual(creations[0][3].get("expiration"), DIX_ANS)

    def test_rotation_records_the_new_expiration(self):
        tenant = self._tenant_cree()
        self._tourne(tenant)
        self.assertEqual(tenant.token_expires_at.strftime("%Y-%m-%dT%H:%M:%S.%f"), EXPIRATION)

    def test_rotation_revokes_the_previous_token(self):
        """Sans révocation, le secret fuité reste vivant : c'est tout l'enjeu."""
        tenant = self._tenant_cree()
        appels = self._tourne(tenant)
        revocations = [a for a in appels if a[1] == "DELETE"]
        self.assertEqual([a[2] for a in revocations], ["/token/" + ANCIEN])
        self.assertTrue(tenant.previous_token_revoked)
        self.assertFalse(tenant.token_revocation_note)

    def test_a_first_rotation_has_nothing_to_revoke(self):
        """Sans jeton précédent, la rotation ne révoque rien et ne le prétend pas."""
        tenant = self._tenant_cree(api_token=False, token_expires_at=False)
        appels = self._tourne(tenant)
        self.assertEqual([a for a in appels if a[1] == "DELETE"], [])
        self.assertEqual(tenant.api_token, NOUVEAU)
        self.assertFalse(tenant.previous_token_revoked)

    # ------------------------------------------------------------------
    # Une révocation ratée ne doit pas faire perdre le jeton neuf
    # ------------------------------------------------------------------

    @mute_logger("odoo.addons.wazo_server.models.wazo_server_tenant")
    def test_a_failed_revocation_keeps_the_new_token_and_says_so(self):
        tenant = self._tenant_cree()
        self._tourne(tenant, revocation_ratee=True)
        self.assertEqual(tenant.api_token, NOUVEAU)
        self.assertFalse(tenant.previous_token_revoked)
        self.assertTrue(tenant.token_revocation_note)
        # Le secret ne se recopie pas dans une note d'échec.
        self.assertNotIn(ANCIEN, tenant.token_revocation_note)

    # ------------------------------------------------------------------
    # Refus lisibles
    # ------------------------------------------------------------------

    def test_rotation_refuses_a_tenant_that_does_not_exist(self):
        brouillon = self._create_tenant()
        with self.assertRaises(UserError) as capture:
            brouillon.action_rotate_token()
        self.assertIn("pas encore", str(capture.exception))

    def test_rotation_refuses_without_admin_credentials(self):
        """Wazo ne rend jamais un mot de passe : sans lui, pas de jeton neuf."""
        tenant = self._tenant_cree(admin_password=False)
        with self.assertRaises(UserError) as capture:
            tenant.action_rotate_token()
        self.assertIn("administrateur", str(capture.exception))

    # ------------------------------------------------------------------
    # La fiche de remise suit
    # ------------------------------------------------------------------

    def test_the_handover_sheet_carries_the_new_token(self):
        tenant = self._tenant_cree()
        self._tourne(tenant)
        fiche = tenant.handover_text
        self.assertIn(NOUVEAU, fiche)
        self.assertNotIn(ANCIEN, fiche)

    # ------------------------------------------------------------------
    # Droits
    # ------------------------------------------------------------------

    def test_a_plain_user_cannot_rotate(self):
        tenant = self._tenant_cree()
        ordinaire = self.env["res.users"].create(
            {"name": "Utilisateur ordinaire", "login": "ordinaire_p7"}
        )
        with self.assertRaises(AccessError):
            tenant.with_user(ordinaire).action_rotate_token()
