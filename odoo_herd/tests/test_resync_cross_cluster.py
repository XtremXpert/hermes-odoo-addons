from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests import tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestResyncCrossCluster(TransactionCase):
    """A staging resync clones its production on the same cluster and
    namespace, and restores the production's latest S3 backup otherwise."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Cluster = cls.env["k8s.cluster"]
        cluster_vals = {
            "api_endpoint": "https://k8s.example.com",
            "kubeconfig": "{}",
            "webhook_base_url": "http://odoo.example.com",
        }
        cls.home = Cluster.create({"name": "home", **cluster_vals})
        cls.cloud = Cluster.create({"name": "cloud", **cluster_vals})
        cls.s3 = cls.env["k8s.s3.config"].create(
            {
                "name": "S3",
                "bucket": "backups",
                "endpoint": "https://s3.example.com",
                "credentials_secret_name": "s3-credentials",
            }
        )
        # A backup's S3 configuration is its cluster's.
        (cls.home | cls.cloud).backup_s3_config_id = cls.s3
        with mute_logger(  # live values read from dummy clusters
            "odoo.addons.odoo_herd.models.k8s_cluster",
            "odoo.addons.odoo_herd.models.k8s_odoo_instance",
        ):
            Instance = cls.env["k8s.odoo.instance"]
            cls.prod = Instance.create(
                {
                    "cluster_id": cls.cloud.id,
                    "name": "shop",
                    "namespace": "shop",
                    "environment": "production",
                }
            )
            cls.local_prod = Instance.create(
                {
                    "cluster_id": cls.home.id,
                    "name": "shop-prod",
                    "namespace": "shop",
                    "environment": "production",
                }
            )
            # Same name and namespace as the production, on another cluster.
            cls.staging = Instance.create(
                {
                    "cluster_id": cls.home.id,
                    "name": "shop",
                    "namespace": "shop",
                    "environment": "staging",
                    "production_instance_id": cls.prod.id,
                }
            )
            cls.env.flush_all()
        cls.Backup = type(cls.env["k8s.odoo.backup"])
        cls.Restore = type(cls.env["k8s.odoo.restore"])
        cls.Refresh = type(cls.env["k8s.odoo.staging.refresh"])

    def setUp(self):
        super().setUp()
        self.enterContext(
            mute_logger(
                "odoo.addons.odoo_herd.models.k8s_cluster",
                "odoo.addons.odoo_herd.models.k8s_odoo_instance",
            )
        )
        # Nothing reaches a cluster: the custom resources are created after
        # commit, which never happens in these tests.
        for model, method in (
            (self.Backup, "_create_backup_job_cr"),
            (self.Restore, "_create_restore_job_cr"),
            (self.Refresh, "_create_refresh_job_cr"),
        ):
            self.enterContext(patch.object(model, method, autospec=True))

    def _backup(self, instance, hours_ago, **vals):
        backup = self.env["k8s.odoo.backup"].create(
            {
                "instance_id": instance.id,
                "format": "zip",
                "with_filestore": True,
                **vals,
            }
        )
        backup.write(
            {
                "state": "completed",
                "object_key": f"shop/{backup.id}.zip",
                "completion_time": fields.Datetime.now() - timedelta(hours=hours_ago),
                **vals,
            }
        )
        return backup

    def test_other_cluster_restores_the_latest_backup(self):
        self._backup(self.prod, 48)
        latest = self._backup(self.prod, 24)
        self._backup(self.prod, 1, with_filestore=False)  # incomplete copy
        self._backup(self.prod, 2, state="failed")
        self._backup(self.local_prod, 0)  # another production

        result = self.staging._herd_resync_from(self.prod)

        self.assertEqual(result._name, "k8s.odoo.restore")
        self.assertEqual(result.backup_id, latest)
        self.assertEqual(result.target_instance_id, self.staging)
        self.assertTrue(result.neutralize)

    def test_other_cluster_without_backup_refuses(self):
        self._backup(self.prod, 1, with_filestore=False)
        with self.assertRaises(UserError):
            self.staging._herd_resync_from(self.prod)
        self.assertFalse(
            self.env["k8s.odoo.restore"].search([("target_instance_id", "=", self.staging.id)])
        )

    def test_other_cluster_keeps_the_filestore(self):
        self._backup(self.prod, 1)
        with self.assertRaises(UserError):
            self.staging._herd_resync_from(self.prod, skip_filestore=True)

    def test_same_location_clones(self):
        staging = self.env["k8s.odoo.instance"].create(
            {
                "cluster_id": self.home.id,
                "name": "shop-staging",
                "namespace": "shop",
                "environment": "staging",
                "production_instance_id": self.local_prod.id,
            }
        )
        result = staging._herd_resync_from(self.local_prod)
        self.assertEqual(result._name, "k8s.odoo.staging.refresh")
        self.assertEqual(result.source_instance_id, self.local_prod)
        self.assertTrue(result.neutralize)

    def test_never_targets_a_production(self):
        with self.assertRaises(UserError):
            self.local_prod._herd_resync_from(self.prod)

    def test_reference_sent_only_on_the_same_location(self):
        """The operator resolves productionInstanceRef in the staging's
        namespace: here it would name the staging itself."""
        spec = self.staging._build_full_patch_data()["spec"]
        self.assertNotIn("productionInstanceRef", spec)

        self.staging.production_instance_id = self.local_prod
        spec = self.staging._build_full_patch_data()["spec"]
        self.assertEqual(spec["productionInstanceRef"], {"name": "shop-prod"})
