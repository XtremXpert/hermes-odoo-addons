import json
from unittest.mock import patch

from odoo.tests import HttpCase
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import CODE
from .common import DIGEST_B
from .common import HerdPortalMixin
from .common import totp_now


@tagged("post_install", "-at_install")
class TestHerdPortal(HerdPortalMixin, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._herd_setup()

    def setUp(self):
        super().setUp()
        self.patch_image = self._herd_mocks()

    def _url(self, suffix=""):
        return f"/my/odoo/{self.prod.id}{suffix}"

    def _post(self, suffix, **data):
        return self.url_open(self._url(suffix), data=dict(data, csrf_token=self.csrf_token()))

    def test_client_sees_production_and_staging(self):
        self.authenticate("herd_client_user", "herd_client_user")
        response = self.url_open("/my/odoo")
        self.assertEqual(response.status_code, 200)
        self.assertIn("shop", response.text)
        response = self.url_open(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertIn("shop-staging", response.text)
        # never the spec, nor the kubeconfig
        self.assertNotIn("kubeconfig", response.text)

    def test_stranger_gets_not_found(self):
        self.authenticate("herd_stranger", "herd_stranger")
        self.assertEqual(self.url_open(self._url()).status_code, 404)
        response = self._post("/resync", staging_id=self.staging.id)
        self.assertEqual(response.status_code, 404)

    def test_actions_refuse_get(self):
        self.authenticate("herd_approver", "herd_approver")
        response = self.url_open(self._url("/resync"), allow_redirects=False)
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(self.env["k8s.odoo.staging.refresh"].search([]))

    def test_same_image_offers_a_modules_only_update(self):
        """After a promotion without its modules, the portal can still ask
        for the module update (PROMO/0045)."""
        self.staging.image = self.prod.image
        self.authenticate("herd_client_user", "herd_client_user")
        page = self.url_open(self._url()).text
        self.assertIn("Update the production's modules", page)
        self.assertNotIn("Move production to this staging's code", page)
        Promotion = self.env["k8s.odoo.promotion"]
        response = self._post("/promote", staging_id=self.staging.id)
        self.assertIn("already runs this staging", response.text)
        self.assertFalse(Promotion.search([("production_id", "=", self.prod.id)]))
        self._post("/promote", staging_id=self.staging.id, modules="sale")
        promotion = Promotion.search([("production_id", "=", self.prod.id)])
        self.assertEqual(promotion.modules, "sale")
        self.assertEqual(promotion.image, promotion.production_image)

    def test_approver_confirms_with_emailed_code(self):
        self.authenticate("herd_client_user", "herd_client_user")
        self._post(
            "/promote",
            staging_id=self.staging.id,
            modules="sale",
            modules_install="project_task_pull_request",
        )
        promotion = self.env["k8s.odoo.promotion"].search([("production_id", "=", self.prod.id)])
        self.assertEqual(promotion.state, "requested")
        self.assertEqual(promotion.modules_install, "project_task_pull_request")
        self.assertEqual(promotion.image, DIGEST_B)

        # a client user who is not an approver sees no confirmation form
        page = self.url_open(self._url()).text
        self.assertNotIn("/confirm", page)

        self.authenticate("herd_approver", "herd_approver")
        self.assertIn("/confirm", self.url_open(self._url()).text)
        self._post(f"/promotion/{promotion.id}/send-code")
        response = self._post(f"/promotion/{promotion.id}/confirm", code="000000")
        self.assertIn("Wrong code", response.text)
        self.assertEqual(promotion.state, "requested")

        self._post(f"/promotion/{promotion.id}/confirm", code=f"{CODE:06d}")
        self.assertEqual(promotion.state, "backing_up")
        self.assertEqual(promotion.confirmed_by_id, self.approver)

    def test_resync_from_portal(self):
        self.authenticate("herd_client_user", "herd_client_user")
        self._post("/resync", staging_id=self.staging.id)
        refresh = self.env["k8s.odoo.staging.refresh"].search(
            [("target_instance_id", "=", self.staging.id)]
        )
        self.assertTrue(refresh.neutralize)
        self.assertEqual(refresh.source_instance_id, self.prod)

    def test_operator_webhook_advances_the_promotion(self):
        promotion = self.env["k8s.odoo.promotion"].browse(
            self.env["k8s.odoo.promotion"]
            .with_user(self.agent)
            .herd_request_promotion(self.staging.id)
        )
        promotion._herd_send_code(self.approver)
        promotion._herd_confirm(self.approver, f"{CODE:06d}")
        backup = promotion.backup_id
        response = self.url_open(
            f"/k8s/backup/webhook/{backup.id}",
            data=json.dumps({"phase": "Completed", "objectKey": "shop/x.zip"}),
            headers={
                "Authorization": f"Bearer {backup.webhook_token}",
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(promotion.state, "done")
        self.patch_image.assert_called_once_with(self.prod, DIGEST_B)

    # --- two-factor authentication ------------------------------------
    def _authenticate_2fa(self, login):
        # Log in without the 2FA step; the confirmation still checks the
        # real TOTP code.
        with patch.object(type(self.env["res.users"]), "_mfa_type", return_value=None):
            self.authenticate(login, login)

    def _agent_request(self, **kw):
        Promotion = self.env["k8s.odoo.promotion"]
        return Promotion.browse(
            Promotion.with_user(self.agent).herd_request_promotion(self.staging.id, **kw)
        )

    def test_totp_approver_confirms_with_the_app_code(self):
        self._herd_enable_totp(self.approver)
        promotion = self._agent_request()
        self._authenticate_2fa("herd_approver")
        page = self.url_open(self._url()).text
        self.assertIn("authenticator app", page)
        self.assertNotIn("/send-code", page)

        response = self._post(f"/promotion/{promotion.id}/send-code")
        self.assertIn("authenticator app", response.text)
        self.assertFalse(
            self.env["mail.mail"].sudo().search([("subject", "ilike", promotion.name)])
        )

        response = self._post(f"/promotion/{promotion.id}/confirm", code="000000")
        self.assertIn("Wrong code", response.text)
        self.assertEqual(promotion.state, "requested")

        self._post(f"/promotion/{promotion.id}/confirm", code=totp_now())
        self.assertEqual(promotion.state, "backing_up")
        self.assertEqual(promotion.confirm_method, "totp")
        self.assertEqual(promotion.confirmed_by_id, self.approver)

    def test_totp_code_cannot_be_replayed(self):
        self._herd_enable_totp(self.approver)
        first = self._agent_request()
        self._authenticate_2fa("herd_approver")
        code = totp_now()
        self._post(f"/promotion/{first.id}/confirm", code=code)
        self.assertEqual(first.state, "backing_up")
        first.backup_id.mark_completed()
        self.assertEqual(first.state, "done")

        # Production now runs the staging image: the second request names a module.
        second = self._agent_request(modules="sale")
        # auth_totp logs the replay it refuses: expected here.
        with mute_logger("odoo.addons.auth_totp.models.res_users"):
            response = self._post(f"/promotion/{second.id}/confirm", code=code)
        self.assertIn("Wrong code", response.text)
        self.assertEqual(second.state, "requested")

    def test_required_2fa_shows_how_to_enable_it(self):
        self.prod.herd_require_2fa = True
        self._agent_request()
        self.authenticate("herd_approver", "herd_approver")
        page = self.url_open(self._url()).text
        self.assertIn("/my/security", page)
        self.assertNotIn("/confirm", page)
