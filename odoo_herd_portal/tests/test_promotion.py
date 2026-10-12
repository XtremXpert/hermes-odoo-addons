from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import AccessError
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase
from odoo.tests import new_test_user

from .common import CODE
from .common import DIGEST_A
from .common import DIGEST_B
from .common import HerdPortalMixin


class TestHerdPromotion(HerdPortalMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._herd_setup()

    def setUp(self):
        super().setUp()
        self.patch_image = self._herd_mocks()
        self.Promotion = self.env["k8s.odoo.promotion"]

    def _request(self, user=None, **kw):
        promotion_id = self.Promotion.with_user(user or self.agent).herd_request_promotion(
            self.staging.id, **kw
        )
        return self.Promotion.browse(promotion_id)

    def _confirm(self, promotion, user=None, code=CODE):
        user = user or self.approver
        promotion._herd_send_code(user)
        self.assertTrue(promotion._herd_confirm(user, f"{code:06d}"))

    # --- the full flow -------------------------------------------------
    def test_full_flow_backup_image_modules(self):
        promotion = self._request(modules="sale,project_task_code")
        self.assertEqual(promotion.image, DIGEST_B)
        self.assertTrue(promotion.requested_by_agent)
        self.assertEqual(promotion.state, "requested")

        self._confirm(promotion)
        self.assertEqual(promotion.state, "backing_up")
        self.assertEqual(promotion.confirmed_by_id, self.approver)
        self.assertEqual(promotion.backup_id.instance_id, self.prod)
        self.assertEqual(promotion.previous_image, DIGEST_A)
        self.patch_image.assert_not_called()

        promotion.backup_id.mark_completed()
        self.patch_image.assert_called_once_with(self.prod, DIGEST_B)
        self.assertEqual(self.prod.image, DIGEST_B)
        self.assertEqual(promotion.state, "upgrading")
        self.assertEqual(promotion.upgrade_id.modules, "sale,project_task_code")

        promotion.upgrade_id.mark_completed()
        self.assertEqual(promotion.state, "done")

    def test_module_update_waits_for_the_rollout(self):
        """PROMO/0017: started while the pods restarted on the new image, the
        update timed out on the registry lock. It now waits for the rollout."""
        self.rolled_out = False
        promotion = self._request(modules="sale")
        self._confirm(promotion)
        promotion.backup_id.mark_completed()
        self.patch_image.assert_called_once_with(self.prod, DIGEST_B)
        self.assertEqual(promotion.state, "deploying")
        self.assertFalse(promotion.upgrade_id)
        self.Promotion._cron_herd_promotions()
        self.assertEqual(promotion.state, "deploying")
        self.rolled_out = True
        self.Promotion._cron_herd_promotions()
        self.assertEqual(promotion.state, "upgrading")
        self.assertEqual(promotion.upgrade_id.modules, "sale")

    def test_same_image_updates_modules_at_once(self):
        """Production already on the staging image (retry of a failed update):
        no image patch, no restart to wait for."""
        self.live_images[self.prod.id] = DIGEST_B
        self.rolled_out = False
        promotion = self._request(modules="sale")
        self._confirm(promotion)
        promotion.backup_id.mark_completed()
        self.patch_image.assert_not_called()
        self.assertEqual(promotion.state, "upgrading")

    def test_same_image_without_modules_is_refused(self):
        """Same image and nothing to update: the request would only back up."""
        self.live_images[self.prod.id] = DIGEST_B
        with self.assertRaisesRegex(UserError, "already runs this staging's code"):
            self._request()
        self.assertFalse(self.Promotion.search([("production_id", "=", self.prod.id)]))
        self.assertEqual(self._request(modules_install="sale").modules_install, "sale")

    def test_without_modules_no_upgrade_job(self):
        promotion = self._request()
        self._confirm(promotion)
        promotion.backup_id.mark_completed()
        self.assertEqual(promotion.state, "done")
        self.assertFalse(promotion.upgrade_id)

    def test_failed_backup_leaves_production_untouched(self):
        promotion = self._request()
        self._confirm(promotion)
        promotion.backup_id.mark_failed(message="S3 unreachable")
        self.assertEqual(promotion.state, "failed")
        self.assertIn("S3 unreachable", promotion.message)
        self.patch_image.assert_not_called()
        self.assertEqual(self.prod.image, DIGEST_A)

    def test_failed_upgrade_keeps_previous_image_for_rollback(self):
        promotion = self._request(modules="sale")
        self._confirm(promotion)
        promotion.backup_id.mark_completed()
        promotion.upgrade_id.mark_failed(message="boom")
        self.assertEqual(promotion.state, "failed")
        self.assertIn(DIGEST_A, promotion.message)

    def test_scheduled_promotion_waits_for_its_time(self):
        when = fields.Datetime.now() + timedelta(hours=2)
        promotion = self._request(scheduled_at=when)
        self._confirm(promotion)
        self.assertEqual(promotion.state, "scheduled")
        self.assertFalse(promotion.backup_id)
        self.Promotion._cron_herd_promotions()
        self.assertEqual(promotion.state, "scheduled")
        with freeze_time(when + timedelta(minutes=1)):
            self.Promotion._cron_herd_promotions()
        self.assertEqual(promotion.state, "backing_up")

    def test_stuck_promotion_times_out(self):
        promotion = self._request()
        self._confirm(promotion)
        with freeze_time(fields.Datetime.now() + timedelta(hours=7)):
            self.Promotion._cron_herd_promotions()
        self.assertEqual(promotion.state, "failed")
        self.patch_image.assert_not_called()

    # --- the human gate ------------------------------------------------
    def test_agent_can_never_confirm(self):
        self.prod.herd_approver_ids |= self.agent
        promotion = self._request()
        with self.assertRaises(AccessError):
            promotion._herd_send_code(self.agent)
        with self.assertRaises(AccessError):
            promotion._herd_confirm(self.agent, f"{CODE:06d}")
        self.assertEqual(promotion.state, "requested")

    def test_client_user_who_is_not_approver_cannot_confirm(self):
        promotion = self._request(user=self.client_user)
        with self.assertRaises(AccessError):
            promotion._herd_send_code(self.client_user)

    def test_wrong_code_and_attempt_limit(self):
        promotion = self._request()
        promotion._herd_send_code(self.approver)
        for _attempt in range(5):
            # inside a savepoint, like any caller rolling back on error
            with self.env.cr.savepoint():
                self.assertFalse(promotion._herd_confirm(self.approver, "000000"))
        self.assertEqual(promotion.sudo().code_attempts, 5)
        with self.assertRaisesRegex(UserError, "Too many"):
            promotion._herd_confirm(self.approver, f"{CODE:06d}")
        self.assertEqual(promotion.state, "requested")

    def test_expired_code(self):
        promotion = self._request()
        promotion._herd_send_code(self.approver)
        with freeze_time(fields.Datetime.now() + timedelta(minutes=11)):
            with self.assertRaisesRegex(UserError, "expired"):
                promotion._herd_confirm(self.approver, f"{CODE:06d}")

    def test_code_is_not_readable(self):
        promotion = self._request()
        promotion._herd_send_code(self.approver)
        with self.assertRaises(AccessError):
            promotion.with_user(self.agent).read(["code_hash"])
        self.assertNotIn(str(CODE), promotion.sudo().code_hash)
        messages = promotion.message_ids.mapped("body")
        self.assertFalse([b for b in messages if str(CODE) in b])

    def test_change_before_confirmation_voids_the_code(self):
        promotion = self._request()
        promotion._herd_send_code(self.approver)
        promotion.sudo().modules = "sale"
        with self.assertRaisesRegex(UserError, "code first"):
            promotion._herd_confirm(self.approver, f"{CODE:06d}")

    def test_confirmed_promotion_is_frozen(self):
        promotion = self._request()
        self._confirm(promotion)
        with self.assertRaises(UserError):
            promotion.sudo().write({"image": DIGEST_A})
        with self.assertRaises(UserError):
            promotion.sudo().write({"modules": "base"})

    def test_promotion_never_starts_unconfirmed(self):
        promotion = self._request()
        with self.assertRaises(AccessError):
            promotion._herd_start()

    def test_confirmation_is_not_reachable_over_rpc(self):
        from odoo.orm.models import get_public_method

        for method in ("_herd_confirm", "_herd_send_code", "_herd_start"):
            with self.assertRaises(AccessError):
                get_public_method(self.Promotion, method)

    def test_agent_has_no_write_access_on_promotions(self):
        promotion = self._request()
        with self.assertRaises(AccessError):
            promotion.with_user(self.agent).write({"state": "scheduled"})

    # --- what agents may and may not do --------------------------------
    def test_tag_image_is_refused(self):
        self.staging.image = "ghcr.io/client/shop:latest"
        with self.assertRaises(ValidationError):
            self._request()

    def test_agent_needs_a_staging_opened_to_agents(self):
        self.staging.herd_agent_allowed = False
        with self.assertRaises(AccessError):
            self._request()
        with self.assertRaises(AccessError):
            self.Promotion.with_user(self.agent).herd_resync_staging(self.staging.id)

    def test_resync_is_neutralized_from_its_own_production(self):
        refresh_id = self.Promotion.with_user(self.agent).herd_resync_staging(self.staging.id)
        refresh = self.env["k8s.odoo.staging.refresh"].browse(refresh_id)
        self.assertTrue(refresh.neutralize)
        self.assertEqual(refresh.source_instance_id, self.prod)
        self.assertEqual(refresh.target_instance_id, self.staging)

    def test_resync_of_another_cluster_restores_the_latest_backup(self):
        """The production on another cluster: its latest S3 backup is restored."""
        cloud = self.cluster.copy({"name": "cloud-cluster"})
        s3 = self.env["k8s.s3.config"].create(
            {
                "name": "S3",
                "bucket": "backups",
                "endpoint": "https://s3.example.com",
                "credentials_secret_name": "s3",
            }
        )
        cloud.backup_s3_config_id = s3
        self.prod.cluster_id = cloud
        backup = self.env["k8s.odoo.backup"].create(
            {"instance_id": self.prod.id, "format": "zip", "with_filestore": True}
        )
        backup.write({"state": "completed", "object_key": "shop/latest.zip"})

        restore_id = self.Promotion.with_user(self.agent).herd_resync_staging(self.staging.id)

        restore = self.env["k8s.odoo.restore"].browse(restore_id)
        self.assertEqual(restore.backup_id, backup)
        self.assertEqual(restore.target_instance_id, self.staging)
        self.assertTrue(restore.neutralize)

    def test_resync_never_targets_production(self):
        with self.assertRaises((AccessError, UserError)):
            self.Promotion.with_user(self.agent).herd_resync_staging(self.prod.id)
        with self.assertRaises(UserError):
            self.Promotion.with_user(self.approver).herd_resync_staging(self.prod.id)

    def test_agent_deploys_staging_but_never_production(self):
        Promotion = self.Promotion.with_user(self.agent)
        Promotion.herd_deploy_staging(self.staging.id, DIGEST_A)
        self.patch_image.assert_called_once_with(self.staging, DIGEST_A)
        with self.assertRaises(AccessError):
            Promotion.herd_deploy_staging(self.prod.id, DIGEST_B)
        with self.assertRaises(ValidationError):
            Promotion.herd_deploy_staging(self.staging.id, "odoo:20.0")

    # --- delivery of a staging by the CI ---------------------------------
    def test_staging_modules_update_waits_for_the_rollout(self):
        Promotion = self.Promotion.with_user(self.agent)
        self.rolled_out = False
        Promotion.herd_deploy_staging(self.staging.id, DIGEST_A, modules=["sale", "project"])
        status = Promotion.herd_staging_status(self.staging.id)
        self.assertEqual(status["modules"], "sale,project")
        self.assertFalse(status["rolled_out"])
        self.assertFalse(status["upgrade_state"])
        self.assertFalse(self.staging.herd_deploy_upgrade_id)

        self.rolled_out = True
        status = Promotion.herd_staging_status(self.staging.id)
        upgrade = self.staging.herd_deploy_upgrade_id
        self.assertEqual(upgrade.instance_id, self.staging)
        self.assertEqual(upgrade.modules, "sale,project")
        self.assertEqual(status["upgrade_state"], upgrade.state)
        # the cron does not start a second update
        self.Promotion._cron_herd_promotions()
        self.assertEqual(
            self.env["k8s.odoo.upgrade"].search_count([("instance_id", "=", self.staging.id)]), 1
        )
        upgrade.mark_completed()
        status = Promotion.herd_staging_status(self.staging.id)
        self.assertEqual(status["upgrade_state"], "completed")

    def test_cron_starts_the_staging_update_after_the_rollout(self):
        self.rolled_out = False
        self.Promotion.with_user(self.agent).herd_deploy_staging(
            self.staging.id, DIGEST_A, modules="sale"
        )
        self.Promotion._cron_herd_promotions()
        self.assertFalse(self.staging.herd_deploy_upgrade_id)
        self.rolled_out = True
        self.Promotion._cron_herd_promotions()
        self.assertEqual(self.staging.herd_deploy_upgrade_id.modules, "sale")

    def test_staging_delivery_never_reaches_a_production(self):
        Promotion = self.Promotion.with_user(self.agent)
        with self.assertRaises(AccessError):
            Promotion.herd_deploy_staging(self.prod.id, DIGEST_B, modules="sale")
        with self.assertRaises(ValidationError):
            Promotion.herd_deploy_staging(self.staging.id, DIGEST_A, modules="sale;drop")
        self.patch_image.assert_not_called()
        with self.assertRaises((AccessError, UserError)):
            Promotion.herd_staging_status(self.prod.id)
        with self.assertRaises(AccessError):
            self.staging.with_user(self.agent).sudo().write({"herd_deploy_modules": "base"})

    def test_staging_status_refuses_a_stranger(self):
        with self.assertRaises(AccessError):
            self.Promotion.with_user(self.stranger).herd_staging_status(self.staging.id)

    def test_replace_cancels_only_the_callers_own_requests(self):
        other_agent = new_test_user(
            self.env,
            login="herd_agent_n2",
            groups="base.group_user,odoo_herd_portal.group_staging_operator",
        )
        human = self._request(user=self.client_user, modules="sale")
        n2 = self._request(user=other_agent, modules="sale")
        first = self._request(modules="sale")
        second = self._request(modules="sale,project", replace=True)
        self.assertEqual(first.state, "cancelled")
        self.assertIn(second.name, first.message_ids[0].body)
        self.assertEqual(second.state, "requested")
        self.assertEqual((human + n2).mapped("state"), ["requested", "requested"])

    def test_replace_never_touches_a_confirmed_promotion(self):
        first = self._request(modules="sale")
        self._confirm(first)
        self._request(modules="project", replace=True)
        self.assertEqual(first.state, "backing_up")

    def test_agent_cannot_change_a_production_even_with_sudo(self):
        prod = self.prod.with_user(self.agent).sudo()
        with self.assertRaises(AccessError):
            prod.write({"image": DIGEST_B})
        with self.assertRaises(AccessError):
            prod.write({"herd_approver_ids": [(4, self.agent.id)]})
        with self.assertRaises(AccessError):
            self.staging.with_user(self.agent).sudo().write({"environment": "production"})

    def test_stranger_cannot_operate(self):
        with self.assertRaises(AccessError):
            self._request(user=self.stranger)
        with self.assertRaises(AccessError):
            self.Promotion.with_user(self.stranger).herd_resync_staging(self.staging.id)

    # --- overlapping and stale promotions -------------------------------
    def test_second_promotion_refused_while_one_runs(self):
        first = self._request()
        second = self._request(user=self.client_user)
        self._confirm(first)
        self.assertEqual(first.state, "backing_up")
        self._confirm(second)
        self.assertEqual(second.state, "failed")
        self.assertIn(first.name, second.message)
        self.assertEqual(
            len(self.env["k8s.odoo.backup"].search([("instance_id", "=", self.prod.id)])), 1
        )

    def test_stale_promotion_never_rolls_production_back(self):
        old = self._request(scheduled_at=fields.Datetime.now() + timedelta(hours=2))
        self._confirm(old)
        # meanwhile, a newer image reached production
        self.prod.image = "ghcr.io/client/shop@sha256:" + "c" * 64
        with freeze_time(fields.Datetime.now() + timedelta(hours=3)):
            self.Promotion._cron_herd_promotions()
        self.assertEqual(old.state, "failed")
        self.assertIn("Production changed", old.message)
        self.assertFalse(old.backup_id)

    # --- only spec.image reaches the cluster ----------------------------
    def test_image_patch_sends_only_the_image(self):
        from odoo.addons.odoo_herd_portal.models.k8s_odoo_instance import K8sOdooInstance

        api = MagicMock()
        self.cluster.active = True
        with (
            patch.object(type(self.cluster), "_get_k8s_client", return_value=object()),
            patch(
                "odoo.addons.odoo_herd_portal.models.k8s_odoo_instance.client.CustomObjectsApi",
                return_value=api,
            ),
            patch.object(type(self.prod), "_patch_to_cluster") as full_sync,
        ):
            K8sOdooInstance._herd_patch_image(self.prod, DIGEST_B)
        api.patch_namespaced_custom_object.assert_called_once()
        kwargs = api.patch_namespaced_custom_object.call_args.kwargs
        self.assertEqual(kwargs["body"], {"spec": {"image": DIGEST_B}})
        self.assertEqual((kwargs["namespace"], kwargs["name"]), ("shop", "shop"))
        full_sync.assert_not_called()

    # --- the code never leaks to agents ---------------------------------
    def test_agent_cannot_find_the_code_in_messages(self):
        promotion = self._request()
        # keep the outgoing mail, as if sending had failed
        with patch.object(type(self.env["mail.mail"]), "send"):
            promotion._herd_send_code(self.approver)
        code = f"{CODE:06d}"
        agent_env = self.env(user=self.agent)
        bodies = agent_env["mail.message"].search_read([], ["body"])
        self.assertFalse([m for m in bodies if code in (m["body"] or "")])
        with self.assertRaises(AccessError):
            agent_env["mail.mail"].search_read([], ["body_html"])
        # the mail exists for the mail queue, not for the agent
        self.assertTrue(
            self.env["mail.mail"].sudo().search([("email_to", "ilike", "approver@shop")])
        )

    # --- two-factor authentication ------------------------------------
    def test_totp_user_cannot_fall_back_to_email(self):
        self._herd_enable_totp(self.approver)
        promotion = self._request()
        self.assertEqual(promotion._herd_confirm_method(self.approver), "totp")
        with self.assertRaisesRegex(UserError, "authenticator"):
            promotion._herd_send_code(self.approver)

    def test_required_2fa_refuses_approver_without_it(self):
        self.prod.herd_require_2fa = True
        promotion = self._request()
        self.assertFalse(promotion._herd_confirm_method(self.approver))
        with self.assertRaisesRegex(UserError, "two-factor"):
            promotion._herd_send_code(self.approver)
        with self.assertRaisesRegex(UserError, "two-factor"):
            promotion._herd_confirm(self.approver, "123456")
        self.assertEqual(promotion.state, "requested")

    def test_agent_cannot_lower_the_2fa_requirement(self):
        self.prod.herd_require_2fa = True
        with self.assertRaises(AccessError):
            self.prod.with_user(self.agent).sudo().write({"herd_require_2fa": False})

    # --- new modules to install ----------------------------------------
    def test_install_only_promotion_runs_the_upgrade_job(self):
        promotion = self._request(modules_install=["project_task_pull_request"])
        self._confirm(promotion)
        promotion.backup_id.mark_completed()
        self.assertEqual(promotion.state, "upgrading")
        self.assertEqual(promotion.upgrade_id.modules_install, "project_task_pull_request")
        self.assertFalse(promotion.upgrade_id.modules)
        promotion.upgrade_id.mark_completed()
        self.assertEqual(promotion.state, "done")

    def test_update_and_install_in_one_job(self):
        promotion = self._request(
            modules="sale", modules_install="project_task_code,project_task_pull_request"
        )
        self._confirm(promotion)
        promotion.backup_id.mark_completed()
        self.assertEqual(promotion.upgrade_id.modules, "sale")
        self.assertEqual(
            promotion.upgrade_id.modules_install, "project_task_code,project_task_pull_request"
        )

    def test_invalid_module_to_install_is_refused(self):
        with self.assertRaises(ValidationError):
            self._request(modules_install="good_module,rm -rf")

    def test_modules_to_install_are_frozen_after_confirmation(self):
        promotion = self._request(modules_install="project_task_code")
        self._confirm(promotion)
        with self.assertRaises(UserError):
            promotion.sudo().write({"modules_install": "base"})

    # --- the live image, never a stale stored field --------------------
    def test_request_freezes_the_image_the_cluster_runs(self):
        live = "ghcr.io/client/shop@sha256:" + "d" * 64
        self.live_images[self.staging.id] = live  # stored field still says DIGEST_B
        promotion = self._request()
        self.assertEqual(promotion.image, live)
        self.assertEqual(promotion.production_image, DIGEST_A)

    def test_start_compares_with_the_live_production_image(self):
        promotion = self._request(scheduled_at=fields.Datetime.now() + timedelta(hours=1))
        self._confirm(promotion)
        # production changed on the cluster, stored field untouched
        self.live_images[self.prod.id] = "ghcr.io/client/shop@sha256:" + "e" * 64
        with freeze_time(fields.Datetime.now() + timedelta(hours=2)):
            self.Promotion._cron_herd_promotions()
        self.assertEqual(promotion.state, "failed")
        self.assertIn("Production changed", promotion.message)
        self.patch_image.assert_not_called()

    def test_unreadable_cluster_refuses_the_request(self):
        self.live_images[self.staging.id] = None
        type(self.env["k8s.odoo.instance"])._herd_live_image.side_effect = lambda inst: (
            _ for _ in ()
        ).throw(UserError("Cannot read the image"))
        with self.assertRaisesRegex(UserError, "Cannot read the image"):
            self._request()

    def test_sync_to_cluster_never_sends_a_production_image(self):
        self.prod.image = DIGEST_B
        with self.assertRaises(UserError):
            self.prod._build_patch_data()
        self.staging.image = DIGEST_A  # a staging image may be synced
        self.assertEqual(self.staging._build_patch_data()["spec"], {"image": DIGEST_A})
