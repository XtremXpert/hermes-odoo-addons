# Part of the wazo_tenant Odoo module. See LICENSE for details.
"""Tableau de bord d'exploitation : agrégats des usagers, groupes, journal."""

from datetime import datetime
from datetime import timedelta

from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("wazo_tenant", "post_install", "-at_install")
class TestTenantDashboard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Dashboard = cls.env["wazo.tenant.dashboard"]
        cls.User = cls.env["wazo.user"]
        cls.Group = cls.env["wazo.ring.group"]
        cls.Cdr = cls.env["wazo.cdr"]
        # wazo_cdr_id est unique : un timestamp d'horloge collerait deux
        # appels créés dans la même seconde.
        cls._cdr_seq = 0

    def _cdr(self, minutes_ago, answered=True):
        type(self)._cdr_seq += 1
        return self.Cdr.create(
            {
                "wazo_cdr_id": self._cdr_seq,
                "date_start": datetime.now() - timedelta(minutes=minutes_ago),
                "date_end": datetime.now() - timedelta(minutes=minutes_ago),
                "answered": answered,
                "duration": 60,
                "caller_num": "1000",
                "destination_num": "2000",
                "call_direction": "outbound",
            }
        )

    def test_empty_dashboard_counts_zeros(self):
        data = self.Dashboard.get_tenant_dashboard()
        self.assertEqual(data["users"]["total"], 0)
        self.assertEqual(data["groups"]["total"], 0)
        self.assertEqual(data["calls"]["total"], 0)
        self.assertFalse(data["calls"]["last_cdr"])

    def test_user_and_group_states(self):
        self.User.create({"name": "Alice", "wazo_state": "synced"})
        self.User.create({"name": "Bob", "wazo_state": "error"})
        group = self.Group.create({"name": "Accueil", "wazo_state": "synced"})
        data = self.Dashboard.get_tenant_dashboard()
        self.assertEqual(data["users"]["total"], 2)
        self.assertEqual(data["users"]["states"]["synced"], 1)
        self.assertEqual(data["users"]["states"]["error"], 1)
        self.assertEqual(data["groups"]["states"]["synced"], 1)
        # Groupe sans membre : l'alerte silencieuse.
        self.assertEqual(data["groups"]["empty"], 1)
        self.assertEqual(group.member_count, 0)

    def test_calls_window_and_recent(self):
        self._cdr(minutes_ago=10, answered=True)
        self._cdr(minutes_ago=20, answered=False)
        self._cdr(minutes_ago=10 * 24 * 60, answered=True)  # hors fenêtre
        data = self.Dashboard.get_tenant_dashboard()
        self.assertEqual(data["calls"]["total"], 2)
        self.assertEqual(data["calls"]["missed"], 1)
        self.assertEqual(len(data["calls"]["recent"]), 2)
        # Le plus récent d'abord.
        self.assertTrue(data["calls"]["recent"][0]["answered"])
        self.assertFalse(data["calls"]["recent"][1]["answered"])
        self.assertTrue(data["calls"]["last_cdr"])

    def test_last_cdr_excluded_when_outside_window(self):
        """Hors fenêtre ou pas : la fraîcheur suit l'entrée la plus
        récente **de tout** le journal, pas seulement la fenêtre."""
        vieux = self._cdr(minutes_ago=10 * 24 * 60, answered=True)
        data = self.Dashboard.get_tenant_dashboard()
        self.assertEqual(data["calls"]["total"], 0)
        self.assertIn(
            vieux.date_start.isoformat(), data["calls"]["last_cdr"]
        )
