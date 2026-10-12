import base64
import time
from contextlib import ExitStack
from unittest.mock import patch

from odoo.tests import new_test_user

DIGEST_A = "ghcr.io/client/shop@sha256:" + "a" * 64
DIGEST_B = "ghcr.io/client/shop@sha256:" + "b" * 64
CODE = 123456
TOTP_SECRET = base64.b32encode(b"herd-portal-totp-key").decode()


def totp_now(offset=0):
    from odoo.addons.auth_totp.models.totp import TIMESTEP
    from odoo.addons.auth_totp.models.totp import hotp

    counter = int(time.time() // TIMESTEP) + offset
    return f"{hotp(base64.b32decode(TOTP_SECRET), counter):06d}"


class HerdPortalMixin:
    """A client production and its staging on an inactive cluster: nothing
    reaches Kubernetes, every custom resource creation is mocked."""

    @classmethod
    def _herd_setup(cls):
        env = cls.env
        cls.client = env["res.partner"].create({"name": "Shop Inc.", "is_company": True})
        cls.other_client = env["res.partner"].create({"name": "Other Inc.", "is_company": True})
        cls.cluster = env["k8s.cluster"].create(
            {
                "name": "test-cluster",
                "api_endpoint": "https://k8s.example.com",
                "kubeconfig": "{}",
                "default_namespace": "shop",
                "webhook_base_url": "http://odoo.example.com",
                "active": False,
            }
        )
        cls.approver = new_test_user(
            env,
            login="herd_approver",
            groups="base.group_portal",
            email="approver@shop.example.com",
            name="Approver",
        )
        cls.approver.partner_id.parent_id = cls.client
        cls.client_user = new_test_user(
            env,
            login="herd_client_user",
            groups="base.group_portal",
            email="user@shop.example.com",
            name="Client user",
        )
        cls.client_user.partner_id.parent_id = cls.client
        cls.stranger = new_test_user(
            env,
            login="herd_stranger",
            groups="base.group_portal",
            email="someone@other.example.com",
            name="Stranger",
        )
        cls.stranger.partner_id.parent_id = cls.other_client
        cls.agent = new_test_user(
            env,
            login="herd_agent",
            groups="base.group_user,odoo_herd_portal.group_staging_operator",
            email="agent@example.com",
            name="Agent N2",
        )
        Instance = env["k8s.odoo.instance"]
        cls.prod = Instance.create(
            {
                "cluster_id": cls.cluster.id,
                "name": "shop",
                "namespace": "shop",
                "environment": "production",
                "image": DIGEST_A,
                "herd_partner_id": cls.client.id,
                "herd_approver_ids": [(6, 0, cls.approver.ids)],
            }
        )
        cls.staging = Instance.create(
            {
                "cluster_id": cls.cluster.id,
                "name": "shop-staging",
                "namespace": "shop",
                "environment": "staging",
                "production_instance_id": cls.prod.id,
                "image": DIGEST_B,
                "herd_agent_allowed": True,
            }
        )

    def _herd_mocks(self):
        """Mock the custom resources and the image patch; return the patch mock."""
        stack = ExitStack()
        self.addCleanup(stack.close)
        env = self.env
        stack.enter_context(patch.object(type(env["k8s.odoo.backup"]), "_create_backup_job_cr"))
        stack.enter_context(patch.object(type(env["k8s.odoo.upgrade"]), "_trigger_upgrade"))
        stack.enter_context(
            patch.object(type(env["k8s.odoo.staging.refresh"]), "_create_refresh_job_cr")
        )
        stack.enter_context(patch.object(type(env["k8s.odoo.restore"]), "_create_restore_job_cr"))
        stack.enter_context(
            patch(
                "odoo.addons.odoo_herd_portal.models.k8s_odoo_promotion.secrets.randbelow",
                return_value=CODE,
            )
        )
        # Inactive cluster: the live image is the stored one, unless a test
        # sets self.live_images[instance] to simulate a lagging stored field.
        self.live_images = {}
        stack.enter_context(
            patch.object(
                type(env["k8s.odoo.instance"]),
                "_herd_live_image",
                autospec=True,
                side_effect=lambda inst: self.live_images.get(inst.id, inst.image),
            )
        )
        # The new image is rolled out unless a test says otherwise.
        self.rolled_out = True
        stack.enter_context(
            patch.object(
                type(env["k8s.odoo.instance"]),
                "_herd_rollout_done",
                autospec=True,
                side_effect=lambda inst, image: self.rolled_out,
            )
        )
        return stack.enter_context(
            patch.object(type(env["k8s.odoo.instance"]), "_herd_patch_image", autospec=True)
        )

    def _herd_enable_totp(self, user):
        user.sudo().totp_secret = TOTP_SECRET
