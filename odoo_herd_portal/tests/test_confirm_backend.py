import json
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.exceptions import UserError
from odoo.tests import HttpCase
from odoo.tests import new_test_user
from odoo.tests import tagged

from .common import CODE
from .common import HerdPortalMixin
from .common import totp_now


@tagged("post_install", "-at_install")
class TestHerdConfirmBackend(HerdPortalMixin, HttpCase):
    """The backend wizard applies the portal's checks: human approver,
    authenticator app or e-mailed code, attempts counted."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._herd_setup()
        cls.admin_approver = new_test_user(
            cls.env,
            login="herd_admin_approver",
            groups="base.group_user,odoo_herd.group_k8s_manager",
            email="admin-approver@example.com",
            name="Admin approver",
        )
        cls.prod.herd_approver_ids += cls.admin_approver
        cls.agent.group_ids += cls.env.ref("odoo_herd.group_k8s_manager")
        cls.prod.herd_approver_ids += cls.agent

    def setUp(self):
        super().setUp()
        self.patch_image = self._herd_mocks()

    def _request(self):
        Promotion = self.env["k8s.odoo.promotion"]
        return Promotion.browse(
            Promotion.with_user(self.agent).herd_request_promotion(self.staging.id)
        )

    def _wizard(self, promotion, user):
        action = promotion.with_user(user).action_herd_open_confirm()
        return self.env[action["res_model"]].with_user(user).browse(action["res_id"])

    def test_only_human_approvers_open_it(self):
        promotion = self._request()
        manager = new_test_user(
            self.env,
            login="herd_other_manager",
            groups="base.group_user,odoo_herd.group_k8s_manager",
            email="m@example.com",
        )
        with self.assertRaises(AccessError):
            promotion.with_user(manager).action_herd_open_confirm()  # not an approver
        with self.assertRaises(AccessError):
            promotion.with_user(self.agent).action_herd_open_confirm()  # approver, but an agent

    def test_emailed_code(self):
        promotion = self._request()
        wizard = self._wizard(promotion, self.admin_approver)
        self.assertEqual(wizard.method, "email")
        with self.assertRaises(UserError):
            wizard.action_confirm()  # no code yet
        wizard.code = str(CODE)
        with self.assertRaises(UserError):
            wizard.action_confirm()  # no code asked
        wizard.action_send_code()
        self.assertTrue(wizard.message)
        wizard.code = "000000"
        wizard.action_confirm()
        self.assertEqual(wizard.error, "Wrong code.")
        self.assertEqual(promotion.sudo().code_attempts, 1)
        self.assertEqual(promotion.state, "requested")
        wizard.code = f"{CODE:06d}"
        result = wizard.action_confirm()
        self.assertEqual(result["tag"], "display_notification")
        self.assertEqual(promotion.state, "backing_up")
        self.assertEqual(promotion.confirmed_by_id, self.admin_approver)
        self.assertEqual(promotion.confirm_method, "email")

    def test_totp_through_the_web_client(self):
        """TOTP needs the HTTP request: confirm through call_kw, as the web
        client does."""
        self._herd_enable_totp(self.admin_approver)
        promotion = self._request()
        with patch.object(type(self.env["res.users"]), "_mfa_type", return_value=None):
            self.authenticate("herd_admin_approver", "herd_admin_approver")

        def call(model, method, args, kwargs=None):
            response = self.url_open(
                f"/web/dataset/call_kw/{model}/{method}",
                data=json.dumps(
                    {
                        "params": {
                            "model": model,
                            "method": method,
                            "args": args,
                            "kwargs": kwargs or {},
                        }
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            return response.json()

        action = call("k8s.odoo.promotion", "action_herd_open_confirm", [[promotion.id]])["result"]
        wizard_id = action["res_id"]
        Wizard = "k8s.odoo.promotion.confirm"
        call(Wizard, "write", [[wizard_id], {"code": "000000"}])
        call(Wizard, "action_confirm", [[wizard_id]])
        self.assertEqual(promotion.state, "requested")
        call(Wizard, "write", [[wizard_id], {"code": totp_now()}])
        result = call(Wizard, "action_confirm", [[wizard_id]])["result"]
        self.assertEqual(result["tag"], "display_notification")
        self.assertEqual(promotion.state, "backing_up")
        self.assertEqual(promotion.confirm_method, "totp")
