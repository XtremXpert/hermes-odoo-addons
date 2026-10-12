import json

from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests import tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestSyncEditedFields(TransactionCase):
    """ "Sync to Cluster" sends the fields changed here only: a field that a
    sync from the cluster never refreshed must not roll the cluster back."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cluster = cls.env["k8s.cluster"].create(
            {
                "name": "test-cluster",
                "api_endpoint": "https://k8s.example.com",
                "kubeconfig": "{}",
                "active": False,
            }
        )
        cls.instance = cls.env["k8s.odoo.instance"].create(
            {
                "cluster_id": cluster.id,
                "name": "shop",
                "namespace": "shop",
                "environment": "production",
                "image": "ghcr.io/client/shop:old",
                # stale desired host: the cluster moved to shop.example.com since
                "ingress_hosts_editable": "shop-old.example.com",
            }
        )

    def test_nothing_edited_sends_nothing(self):
        with self.assertRaises(UserError):
            self.instance._build_patch_data()

    def test_only_edited_fields_are_sent(self):
        self.instance.replicas = 2
        self.assertEqual(self.instance.edited_fields, "replicas")
        patch = self.instance._build_patch_data()
        self.assertEqual(patch, {"spec": {"replicas": 2}})

    def test_fields_of_one_spec_key_go_together(self):
        self.instance.cpu_limit = "2"
        spec = self.instance._build_patch_data()["spec"]
        self.assertEqual(set(spec), {"resources"})

    def test_sync_from_cluster_does_not_mark(self):
        self.instance.write(
            {
                "spec": json.dumps({"filestore": {"storageSize": "40Gi"}}),
                "filestore_size": "40Gi",
            }
        )
        self.assertFalse(self.instance.edited_fields)

    def test_reset_clears(self):
        self.instance.ingress_hosts_editable = "shop.example.com"
        self.assertTrue(self.instance.edited_fields)
        self.instance.action_reset_to_current()
        self.assertFalse(self.instance.edited_fields)

    def test_successful_sync_clears(self):
        self.instance.ingress_hosts_editable = "shop.example.com"
        # inactive cluster: nothing sent, and the warning saying so is expected
        with mute_logger("odoo.addons.odoo_herd.models.k8s_odoo_instance"):
            self.instance.action_sync_to_cluster()
        self.assertFalse(self.instance.edited_fields)
