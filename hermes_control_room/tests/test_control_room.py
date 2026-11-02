# Part of the hermes_control_room Odoo module. See LICENSE for details.

from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestControlRoom(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = cls.env["proxmox.server"].create({
            "name": "test",
            "url": "https://pve.test:8006",
            "api_token": "user@pve!test=secret",
        })
        cls.node = cls.env["proxmox.node"].create({
            "server_id": cls.server.id,
            "name": "pve-test",
            "status": "online",
            "mem_used": 90,
            "mem_max": 100,
        })

    def test_snapshot_has_the_expected_shape(self):
        snapshot = self.env["control.room"].proxmox_snapshot()
        self.assertIn("totals", snapshot)
        self.assertIn("nodes", snapshot)
        self.assertIn("alerts", snapshot)
        self.assertIn("synced_at", snapshot)
        self.assertEqual(snapshot["totals"]["nodes"], 1)

    def test_a_node_near_its_memory_limit_raises_a_warning(self):
        snapshot = self.env["control.room"].proxmox_snapshot()
        warnings = [a for a in snapshot["alerts"] if a["level"] == "warning"]
        self.assertTrue(any("pve-test" in alert["text"] for alert in warnings))

    def test_an_offline_node_raises_a_critical_alert(self):
        self.node.status = "offline"
        snapshot = self.env["control.room"].proxmox_snapshot()
        criticals = [alert for alert in snapshot["alerts"] if alert["level"] == "critical"]
        self.assertTrue(any("pve-test" in alert["text"] for alert in criticals))
