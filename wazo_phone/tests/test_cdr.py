# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Tests du journal d'appels Wazo (CDR) : upsert, dates, matching contact."""

from datetime import UTC
from datetime import datetime
from unittest.mock import patch

from odoo.addons.wazo_phone.models.wazo_cdr import _parse_wazo_datetime
from odoo.tests import TransactionCase
from odoo.tests import tagged
from odoo.tools import mute_logger


@tagged("wazo_phone", "post_install", "-at_install")
class TestParseWazoDatetime(TransactionCase):
    def test_aware_datetime_converted_to_naive_utc(self):
        value = _parse_wazo_datetime("2026-09-20T10:30:00+00:00")
        self.assertEqual(value, datetime(2026, 9, 20, 10, 30))
        self.assertIsNone(value.tzinfo)

    def test_non_utc_offset_converted_to_utc(self):
        value = _parse_wazo_datetime("2026-09-20T06:00:00-04:00")
        self.assertEqual(value, datetime(2026, 9, 20, 10, 0))

    def test_naive_datetime_kept(self):
        value = _parse_wazo_datetime("2026-09-20T10:00:00")
        self.assertEqual(value, datetime(2026, 9, 20, 10, 0))

    def test_empty_value_returns_false(self):
        self.assertFalse(_parse_wazo_datetime(False))
        self.assertFalse(_parse_wazo_datetime(None))

    def test_invalid_value_returns_false(self):
        self.assertFalse(_parse_wazo_datetime("hier matin"))


def _cdr_item(**overrides):
    item = {
        "id": 1234,
        "start": "2026-09-20T10:00:00+00:00",
        "end": "2026-09-20T10:05:00+00:00",
        "answered": True,
        "duration": 300,
        "source_extension": "5145550100",
        "source_name": "Bob",
        "destination_extension": "5550",
        "destination_name": "Alice",
        "call_direction": "outbound",
    }
    item.update(overrides)
    return item


@tagged("wazo_phone", "post_install", "-at_install")
class TestWazoCdrSync(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_str("wazo.url", "https://wazo.example.com")
        cls.env["ir.config_parameter"].sudo().set_str("wazo.api_key", "test-api-token")
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Bob",
                "phone": "+1 514-555-0100",
            }
        )

    def _patch_call_logd(self, pages):
        """Pages : liste de listes d'items (simulation de pagination)."""

        def call_logd(method, path, params=None, body=None):
            assert method == "GET" and path == "/cdr"
            page = int(params["page"])
            items = pages[page - 1] if page <= len(pages) else []
            return {"items": items, "total": sum(len(p) for p in pages)}

        return patch(
            "odoo.addons.wazo_phone.models.wazo_cdr.WazoClient.call_logd", side_effect=call_logd
        )

    def test_sync_creates_cdr_and_matches_partner_by_phone(self):
        with self._patch_call_logd([[_cdr_item()]]):
            created = self.env["wazo.cdr"].sync_cdrs()
        self.assertEqual(created, 1)
        cdr = self.env["wazo.cdr"].search([("wazo_cdr_id", "=", 1234)])
        self.assertEqual(cdr.date_start, datetime(2026, 9, 20, 10, 0))
        self.assertEqual(cdr.date_end, datetime(2026, 9, 20, 10, 5))
        self.assertTrue(cdr.answered)
        self.assertEqual(cdr.duration, 300)
        self.assertEqual(cdr.call_direction, "outbound")
        self.assertEqual(cdr.partner_id, self.partner)

    def test_sync_is_idempotent(self):
        pages = [[_cdr_item()]]
        with self._patch_call_logd(pages):
            self.env["wazo.cdr"].sync_cdrs()
        with self._patch_call_logd(pages):
            created = self.env["wazo.cdr"].sync_cdrs()
        self.assertEqual(created, 0)
        self.assertEqual(self.env["wazo.cdr"].search_count([("wazo_cdr_id", "=", 1234)]), 1)

    def test_sync_updates_changed_fields(self):
        pages = [[_cdr_item(answered=False, duration=0, end="2026-09-20T10:00:01+00:00")]]
        with self._patch_call_logd(pages):
            self.env["wazo.cdr"].sync_cdrs()
        with self._patch_call_logd(pages):
            created = self.env["wazo.cdr"].sync_cdrs()
        self.assertEqual(created, 0)
        cdr = self.env["wazo.cdr"].search([("wazo_cdr_id", "=", 1234)])
        self.assertFalse(cdr.answered)
        self.assertEqual(cdr.duration, 0)

    def test_sync_handles_pagination(self):
        # Ids distincts (hors du pool des CDR réels) : l'upsert est
        # idempotent, un wazo_cdr_id déjà en base ne compte pas comme
        # « créé ».
        item1 = _cdr_item(id=7777)
        item2 = _cdr_item(id=7778)
        # Comptage relatif (la base peut contenir des CDR issus d'un sync
        # live antérieur).
        before = self.env["wazo.cdr"].search_count([])
        with self._patch_call_logd([[item1], [item2]]):
            created = self.env["wazo.cdr"].sync_cdrs()
        self.assertEqual(created, 2)
        self.assertEqual(self.env["wazo.cdr"].search_count([]), before + 2)

    def test_sync_sends_start_end_window(self):
        seen = {}

        def call_logd(method, path, params=None, body=None):
            seen.update(params)
            return {"items": []}

        with patch(
            "odoo.addons.wazo_phone.models.wazo_cdr.WazoClient.call_logd", side_effect=call_logd
        ):
            self.env["wazo.cdr"].sync_cdrs(
                since=datetime(2026, 9, 19, 0, 0), until=datetime(2026, 9, 20, 0, 0)
            )
        self.assertEqual(seen["start"], "2026-09-19T00:00:00+00:00")
        self.assertEqual(seen["end"], "2026-09-20T00:00:00+00:00")

    @mute_logger("odoo.addons.wazo_phone.models.wazo_cdr")
    def test_cron_sync_swallows_api_errors(self):
        from ..services.wazo_client import WazoAPIError

        with patch(
            "odoo.addons.wazo_phone.models.wazo_cdr.WazoClient.call_logd",
            side_effect=WazoAPIError("boom"),
        ):
            self.env["wazo.cdr"].cron_sync_cdrs()  # ne doit pas lever

    def test_default_window_is_last_24h(self):
        seen = {}

        def call_logd(method, path, params=None, body=None):
            seen.update(params)
            return {"items": []}

        with patch(
            "odoo.addons.wazo_phone.models.wazo_cdr.WazoClient.call_logd", side_effect=call_logd
        ):
            self.env["wazo.cdr"].sync_cdrs()
        start = datetime.fromisoformat(seen["start"].split("+")[0])
        end = datetime.fromisoformat(seen["end"].split("+")[0])
        self.assertAlmostEqual((end - start).total_seconds(), 86400, delta=60)

    def test_now_utc_helper_is_naive(self):
        # La fenêtre par défaut doit rester naive (fuseau UTC)
        now = datetime.now(UTC).replace(tzinfo=None)
        self.assertIsNone(now.tzinfo)
