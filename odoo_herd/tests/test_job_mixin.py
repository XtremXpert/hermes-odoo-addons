from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

from kubernetes.client.rest import ApiException

from odoo import fields
from odoo.tests import TransactionCase
from odoo.tests import tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestJobMixin(TransactionCase):
    """Operator jobs: custom resource created after commit, state read back
    from the cluster when the webhook is lost."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cluster = cls.env["k8s.cluster"].create(
            {
                "name": "test-cluster",
                "api_endpoint": "https://k8s.example.com",
                "kubeconfig": "{}",
                "webhook_base_url": "http://odoo.example.com",
            }
        )
        with mute_logger(  # live values read from a dummy cluster
            "odoo.addons.odoo_herd.models.k8s_cluster",
            "odoo.addons.odoo_herd.models.k8s_odoo_instance",
        ):
            cls.instance = cls.env["k8s.odoo.instance"].create(
                {
                    "cluster_id": cls.cluster.id,
                    "name": "shop",
                    "namespace": "shop",
                    "environment": "production",
                    "image": "ghcr.io/client/shop:1",
                }
            )
            cls.env.flush_all()
        cls.Upgrade = type(cls.env["k8s.odoo.upgrade"])

    def setUp(self):
        super().setUp()
        # The post-commit callback opens its own cursor: in registry test mode
        # it shares this test's transaction and sees the records created here.
        self.enterContext(self.enter_registry_test_mode())
        # The test cluster is active with a dummy kubeconfig: reading an
        # instance's live values logs a connection error, irrelevant here.
        self.enterContext(
            mute_logger(
                "odoo.addons.odoo_herd.models.k8s_cluster",
                "odoo.addons.odoo_herd.models.k8s_odoo_instance",
            )
        )

    def _upgrade(self):
        return self.env["k8s.odoo.upgrade"].create(
            {"instance_id": self.instance.id, "modules": "sale", "modules_install": ""}
        )

    def _age(self, record, minutes):
        """Pretend the record was last written ``minutes`` ago."""
        past = fields.Datetime.now() - timedelta(minutes=minutes)
        self.env.flush_all()  # a pending ORM write would reset write_date afterwards
        self.env.cr.execute(
            f"UPDATE {record._table} SET write_date = %s, create_date = %s WHERE id = %s",
            (past, past, record.id),
        )
        record.invalidate_recordset(["write_date", "create_date"])

    def test_custom_resource_waits_for_the_commit(self):
        created = []

        def trigger(rec):
            created.append(rec.id)
            rec.upgrade_job_name = "shop-upgrade-abcde"

        with patch.object(self.Upgrade, "_trigger_upgrade", autospec=True, side_effect=trigger):
            upgrade = self._upgrade()
            # nothing reaches the cluster inside the transaction
            self.assertEqual(created, [])
            self.env.cr.postcommit.run()
        self.assertEqual(created, [upgrade.id])
        self.assertEqual(upgrade.upgrade_job_name, "shop-upgrade-abcde")
        self.assertEqual(upgrade.state, "pending")

    @mute_logger("odoo.addons.odoo_herd.models.k8s_job_mixin")
    def test_creation_error_fails_the_job(self):
        with patch.object(
            self.Upgrade, "_trigger_upgrade", autospec=True, side_effect=RuntimeError("API down")
        ):
            upgrade = self._upgrade()
            self.env.cr.postcommit.run()
        self.assertEqual(upgrade.state, "failed")
        self.assertIn("API down", upgrade.message)

    def _poll_with(self, resource=None, error=None):
        api = MagicMock()
        if error:
            api.get_namespaced_custom_object.side_effect = error
        else:
            api.get_namespaced_custom_object.return_value = resource
        with (
            patch.object(type(self.cluster), "_get_k8s_client", return_value=MagicMock()),
            patch(
                "odoo.addons.odoo_herd.models.k8s_job_mixin.client.CustomObjectsApi",
                return_value=api,
            ),
        ):
            self.env["k8s.odoo.upgrade"]._k8s_job_poll()
        return api

    def test_lost_webhook_is_recovered_from_the_cluster(self):
        with patch.object(self.Upgrade, "_trigger_upgrade", autospec=True):
            upgrade = self._upgrade()
        upgrade.write({"upgrade_job_name": "shop-upgrade-abcde", "state": "running"})
        self._age(upgrade, 5)
        api = self._poll_with(
            {"status": {"phase": "Completed", "completionTime": "2026-10-07T17:07:04Z"}}
        )
        self.assertEqual(
            api.get_namespaced_custom_object.call_args.kwargs["name"], "shop-upgrade-abcde"
        )
        self.assertEqual(
            api.get_namespaced_custom_object.call_args.kwargs["plural"], "odooupgradejobs"
        )
        self.assertEqual(upgrade.state, "completed")

    def test_recent_jobs_are_left_to_the_webhook(self):
        with patch.object(self.Upgrade, "_trigger_upgrade", autospec=True):
            upgrade = self._upgrade()
        upgrade.write({"upgrade_job_name": "shop-upgrade-abcde", "state": "running"})
        api = self._poll_with({"status": {"phase": "Completed"}})
        api.get_namespaced_custom_object.assert_not_called()
        self.assertEqual(upgrade.state, "running")

    def test_failed_and_vanished_jobs(self):
        with patch.object(self.Upgrade, "_trigger_upgrade", autospec=True):
            failed, vanished = self._upgrade(), self._upgrade()
        failed.write({"upgrade_job_name": "shop-upgrade-1", "state": "running"})
        self._age(failed, 5)
        self._poll_with({"status": {"phase": "Failed", "message": "module error"}})
        self.assertEqual(failed.state, "failed")
        self.assertEqual(failed.message, "module error")

        vanished.write({"upgrade_job_name": "shop-upgrade-2", "state": "running"})
        self._age(vanished, 5)
        self._poll_with(error=ApiException(status=404))
        self.assertEqual(vanished.state, "failed")

    def test_job_never_created(self):
        with patch.object(self.Upgrade, "_trigger_upgrade", autospec=True):
            upgrade = self._upgrade()
        self._age(upgrade, 20)
        self._poll_with({"status": {}})
        self.assertEqual(upgrade.state, "failed")

    def test_backup_completion_keeps_the_object_key(self):
        Backup = type(self.env["k8s.odoo.backup"])
        with patch.object(Backup, "_create_backup_job_cr", autospec=True):
            backup = self.env["k8s.odoo.backup"].create(
                {"instance_id": self.instance.id, "format": "zip", "with_filestore": True}
            )
        backup.write({"backup_job_name": "shop-backup-abcde", "state": "running"})
        self._age(backup, 5)
        api = MagicMock()
        api.get_namespaced_custom_object.return_value = {
            "status": {"phase": "Completed", "objectKey": "shop/20261007.zip"}
        }
        with (
            patch.object(type(self.cluster), "_get_k8s_client", return_value=MagicMock()),
            patch(
                "odoo.addons.odoo_herd.models.k8s_job_mixin.client.CustomObjectsApi",
                return_value=api,
            ),
        ):
            self.env["k8s.odoo.backup"]._k8s_job_poll()
        self.assertEqual(backup.state, "completed")
        self.assertEqual(
            api.get_namespaced_custom_object.call_args.kwargs["plural"], "odoobackupjobs"
        )

    def test_creation_keeps_the_callers_sudo(self):
        """A portal user confirms a promotion: the backup is created in sudo
        by the promotion, and its custom resource must be too."""
        portal = self.env["res.users"].create(
            {
                "name": "Portal",
                "login": "herd_job_portal",
                "group_ids": [(6, 0, self.env.ref("base.group_portal").ids)],
            }
        )
        Backup = type(self.env["k8s.odoo.backup"])
        seen = []
        with patch.object(
            Backup,
            "_create_backup_job_cr",
            autospec=True,
            side_effect=lambda rec: seen.append(rec.env.su),
        ):
            self.env["k8s.odoo.backup"].with_user(portal).sudo().create(
                {"instance_id": self.instance.id, "format": "zip", "with_filestore": True}
            )
            self.env.cr.postcommit.run()
        self.assertEqual(seen, [True])
