# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Tests du bouclage d'appel et du tableau de bord.

Couvre :

* ``res.users.notify_wazo_incoming_call`` — relais d'un appel entrant sur le
  canal bus de l'utilisateur (P3.3g) ;
* ``res.users.finalize_wazo_call`` — note sur le contact identifié,
  activité « Appel » et notification bus pour un entrant manqué ;
* ``wazo.cdr.get_wazo_dashboard`` — compteurs des périmètres « mes appels »
  (poste de l'utilisateur) et « équipe » (gestionnaire seulement).
"""

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("wazo_phone", "post_install", "-at_install")
class TestCallFlow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create(
            {
                "name": "Agent Test",
                "login": "wazo_agent_test",
                "group_ids": [(4, cls.env.ref("wazo_tenant.group_wazo_user").id)],
            }
        )
        cls.wizo = cls.env["wazo.user"].create(
            {
                "name": "Agent Test",
                "partner_id": cls.user.partner_id.id,
                "extension": "1011",
                "wazo_state": "synced",
                "sip_username": "1011",
            }
        )
        cls.user.partner_id.wazo_user_id = cls.wizo
        cls.caller = cls.env["res.partner"].create(
            {"name": "Client Alpha", "phone": "+1 514-555-0100"}
        )

    def _bus_spy(self):
        """Capture ``bus.bus._sendone`` : liste (canal, type, message)."""
        sent = []
        original = self.env["bus.bus"]._sendone

        def spy(bus, target, notification_type, message):
            sent.append((target, notification_type, message))
            return original(target, notification_type, message)

        return sent, patch(
            "odoo.addons.bus.models.bus.BusBus._sendone", autospec=True, side_effect=spy
        )

    def _cdr(self, wazo_id, **overrides):
        values = {
            "wazo_cdr_id": wazo_id,
            "date_start": fields.Datetime.now() - timedelta(hours=1),
            "answered": True,
            "duration": 60,
            "caller_num": "5145550100",
            "destination_num": "1011",
            "call_direction": "inbound",
        }
        values.update(overrides)
        return self.env["wazo.cdr"].create(values)

    # ------------------------------------------------------------------
    # notify_wazo_incoming_call
    # ------------------------------------------------------------------

    def test_notify_incoming_sends_on_user_channel(self):
        sent, bus = self._bus_spy()
        with bus:
            result = self.user.with_user(self.user).notify_wazo_incoming_call(
                {"num": "5145550100", "name": "Client Alpha"}
            )
        self.assertTrue(result)
        self.assertEqual(len(sent), 1)
        channel, notif_type, message = sent[0]
        # Le canal est l'enregistrement res.users de l'appelant (les
        # sessions de l'utilisateur y sont abonnées d'office).
        self.assertEqual(channel, self.user)
        self.assertEqual(notif_type, "wazo_phone.incoming_call")
        self.assertEqual(message["num"], "5145550100")
        self.assertEqual(message["name"], "Client Alpha")

    def test_notify_incoming_accepts_legacy_from_key(self):
        sent, bus = self._bus_spy()
        with bus:
            self.user.notify_wazo_incoming_call({"from": "1012"})
        self.assertEqual(sent[0][2]["num"], "1012")

    # ------------------------------------------------------------------
    # finalize_wazo_call — appel répondu
    # ------------------------------------------------------------------

    def test_finalize_answered_call_notes_the_partner(self):
        result = self.user.finalize_wazo_call(
            {"num": "5145550100", "direction": "inbound", "answered": True, "duration": 150}
        )
        self.assertFalse(result["missed"])
        self.assertEqual(result["partner_id"], self.caller.id)
        message = self.env["mail.message"].search(
            [("model", "=", "res.partner"), ("res_id", "=", self.caller.id)],
            order="id desc",
            limit=1,
        )
        self.assertIn("5145550100", message.body)
        self.assertIn("répondu", message.body)
        self.assertFalse(
            self.env["mail.activity"].search_count(
                [("res_model", "=", "res.partner"), ("res_id", "=", self.caller.id)]
            )
        )

    def test_finalize_outbound_call_matches_destination(self):
        result = self.user.finalize_wazo_call(
            {"num": "5145550100", "direction": "outbound", "answered": True, "duration": 5}
        )
        self.assertEqual(result["partner_id"], self.caller.id)

    # ------------------------------------------------------------------
    # finalize_wazo_call — appel manqué
    # ------------------------------------------------------------------

    def test_finalize_missed_inbound_creates_call_activity(self):
        sent, bus = self._bus_spy()
        with bus:
            result = self.user.finalize_wazo_call(
                {"num": "5145550100", "direction": "inbound", "answered": False}
            )
        self.assertTrue(result["missed"])
        self.assertTrue(result["activity_id"])
        activity = self.env["mail.activity"].browse(result["activity_id"])
        self.assertEqual(activity.res_model, "res.partner")
        self.assertEqual(activity.res_id, self.caller.id)
        self.assertEqual(activity.user_id, self.user)
        self.assertEqual(
            activity.activity_type_id,
            self.env.ref("mail.mail_activity_data_call"),
        )
        missed = [s for s in sent if s[1] == "wazo_phone.missed_call"]
        self.assertEqual(len(missed), 1)
        self.assertEqual(missed[0][2]["num"], "5145550100")
        self.assertEqual(missed[0][2]["partner_id"], self.caller.id)

    def test_finalize_missed_without_partner_notifies_only(self):
        sent, bus = self._bus_spy()
        with bus:
            result = self.user.finalize_wazo_call(
                {"num": "9999", "direction": "inbound", "answered": False}
            )
        self.assertTrue(result["missed"])
        self.assertFalse(result["partner_id"])
        self.assertFalse(result["activity_id"])
        self.assertEqual(
            [s[1] for s in sent].count("wazo_phone.missed_call"), 1
        )

    def test_finalize_unknown_direction_defaults_outbound(self):
        result = self.user.finalize_wazo_call(
            {"num": "5145550100", "direction": "sideways", "answered": True}
        )
        self.assertFalse(result["missed"])
        self.assertEqual(result["partner_id"], self.caller.id)

    # ------------------------------------------------------------------
    # get_wazo_dashboard — périmètres
    # ------------------------------------------------------------------

    def test_dashboard_mine_filters_on_user_extension(self):
        self._cdr(5001, destination_num="1011", answered=False)
        self._cdr(5002, call_direction="outbound", caller_num="1011", destination_num="5145550100")
        self._cdr(5003, destination_num="2000", answered=False)  # autre poste
        dashboard = self.env["wazo.cdr"].with_user(self.user).get_wazo_dashboard(30)
        self.assertEqual(dashboard["extension"], "1011")
        mine = dashboard["mine"]
        self.assertEqual(mine["total"], 2)
        self.assertEqual(mine["missed"], 1)
        self.assertEqual(mine["outbound"], 1)
        self.assertEqual(mine["duration_sum"], 120)

    def test_dashboard_team_requires_manager(self):
        self._cdr(5010, destination_num="2000")
        dashboard = self.env["wazo.cdr"].with_user(self.user).get_wazo_dashboard(30)
        self.assertFalse(dashboard["team"])

    def test_dashboard_team_aggregates_agents(self):
        manager_group = self.env.ref("wazo_tenant.group_wazo_manager")
        self.user.write({"group_ids": [(4, manager_group.id)]})
        self._cdr(5020, destination_num="1011", answered=False)
        self._cdr(5021, call_direction="outbound", caller_num="2000", destination_num="5145550100")
        dashboard = self.env["wazo.cdr"].with_user(self.user).get_wazo_dashboard(30)
        team = dashboard["team"]
        self.assertTrue(team)
        self.assertEqual(team["total"], 2)
        agents = {a["extension"]: a for a in team["agents"]}
        self.assertIn("1011", agents)
        self.assertIn("2000", agents)
        self.assertEqual(agents["1011"]["missed"], 1)
        self.assertEqual(agents["1011"]["name"], "Agent Test")

    def test_dashboard_recent_is_newest_first(self):
        older = self._cdr(5030, date_start=fields.Datetime.now() - timedelta(hours=3))
        newer = self._cdr(5031, date_start=fields.Datetime.now() - timedelta(hours=1))
        dashboard = self.env["wazo.cdr"].with_user(self.user).get_wazo_dashboard(30)
        ids = [e["id"] for e in dashboard["mine"]["recent"]]
        self.assertLess(ids.index(newer.id), ids.index(older.id))

    def test_dashboard_mine_is_empty_without_extension(self):
        self._cdr(5040, destination_num="2000")
        sans_poste = self.env["res.users"].create(
            {
                "name": "Sans Poste",
                "login": "wazo_sans_poste",
                "group_ids": [(4, self.env.ref("wazo_tenant.group_wazo_user").id)],
            }
        )
        dashboard = self.env["wazo.cdr"].with_user(sans_poste).get_wazo_dashboard(30)
        self.assertFalse(dashboard["extension"])
        self.assertEqual(dashboard["mine"]["total"], 0)
        self.assertEqual(dashboard["mine"]["recent"], [])

    def test_dashboard_clamps_days(self):
        dashboard = self.env["wazo.cdr"].with_user(self.user).get_wazo_dashboard("99")
        self.assertEqual(dashboard["days"], 99)
        dashboard = self.env["wazo.cdr"].with_user(self.user).get_wazo_dashboard(9999)
        self.assertEqual(dashboard["days"], 365)
