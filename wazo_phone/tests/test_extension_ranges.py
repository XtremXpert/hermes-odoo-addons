# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Tests des plages d'extensions par contexte (P4.1).

Les plages appartiennent au contexte — donc au tenant — et sont servies
*calculées* par wazo-confd :

    GET /1.1/contexts/{context_id}/ranges/{range_type}?availability=…

``availability=available`` découpe la plage en sous-plages de numéros libres ;
``all`` rend la plage déclarée. Le PBX considère **toute** extension existante
comme indisponible, même non attribuée : on ne recalcule donc jamais la
disponibilité nous-mêmes.

Les bornes sont rendues par l'API sous forme de **chaînes** (``"1000"``), et non
d'entiers : Wazo conserve les extensions en texte pour préserver un éventuel
zéro de tête. Les comparaisons se font donc sur la valeur numérique, sans
jamais renoncer à la forme textuelle — c'est elle qui repart vers l'API.
"""

import io
import json
from unittest.mock import patch

from odoo.addons.wazo_phone.services.wazo_client import WazoClient
from odoo.addons.wazo_phone.services.wazo_client import in_ranges
from odoo.addons.wazo_phone.tests.test_client import WazoClientTestBase
from odoo.tests import tagged

CONTEXTE = "ctx-test-internal-dad46d8d-02df-4cf9-b92c-2f3bc736f039"

# Ce que le PBX réel répond (relevé le 2026-09-24, tenant `test`), bornes en
# chaînes telles quelles.
PLAGES_REELLES = {
    "user": b'{"total": 3, "items": [{"start": "1000", "end": "1000"},'
    b' {"start": "1006", "end": "1010"}, {"start": "1012", "end": "1999"}]}',
    "group": b'{"total": 1, "items": [{"start": "2002", "end": "2099"}]}',
    "queue": b'{"total": 0, "items": []}',
}


class _FakeHTTP:
    """Remplace le gestionnaire de contexte renvoyé par ``urlopen``."""

    def __init__(self, raw):
        self._raw = raw

    def __enter__(self):
        return io.BytesIO(self._raw)

    def __exit__(self, *args):
        return False


class _RangeTestBase(WazoClientTestBase):
    """Base : aiguillage des appels simulés par fragment d'URL."""

    def _patch(self, routes, calls=None):
        """Simule ``urlopen`` selon des couples (fragment d'URL, corps)."""

        def _urlopen(request, *args, **kwargs):
            url = getattr(request, "full_url", None) or str(request)
            if calls is not None:
                calls.append(url)
            for fragment, raw in routes:
                if fragment in url:
                    return _FakeHTTP(raw)
            raise AssertionError("appel non simulé : %s" % url)

        return patch("urllib.request.urlopen", side_effect=_urlopen)

    def _contexts(self, *noms_ids, total=None):
        """Corps de ``GET /contexts`` à partir de couples (nom, id)."""
        items = [{"id": i, "name": nom} for nom, i in noms_ids]
        return json.dumps(
            {
                "total": total if total is not None else len(items),
                "items": items,
            }
        ).encode("utf-8")


@tagged("wazo_phone", "post_install", "-at_install")
class TestContextIdResolution(_RangeTestBase):
    def test_context_id_resolves_name_to_numeric_id(self):
        """Le nom du contexte (porté par les endpoints) donne son id."""
        with self._patch([("/contexts", self._contexts((CONTEXTE, 1)))]):
            self.assertEqual(WazoClient(self.env).context_id(CONTEXTE), 1)

    def test_context_id_is_cached(self):
        """Deux lectures du même contexte ne font qu'un appel."""
        calls = []
        with self._patch([("/contexts", self._contexts((CONTEXTE, 1)))], calls=calls):
            client = WazoClient(self.env)
            client.context_id(CONTEXTE)
            client.context_id(CONTEXTE)
        self.assertEqual(len(calls), 1)

    def test_context_id_returns_none_when_unknown(self):
        """Un contexte inconnu ne lève pas : il rend ``None``."""
        with self._patch([("/contexts", self._contexts(("autre", 2)))]):
            self.assertIsNone(WazoClient(self.env).context_id(CONTEXTE))

    def test_context_id_pages_through_results(self):
        """Un contexte absent de la première page reste trouvable."""
        page1 = json.dumps(
            {
                "total": 150,
                "items": [{"id": i, "name": "ctx-%d" % i} for i in range(100)],
            }
        ).encode("utf-8")
        page2 = self._contexts((CONTEXTE, 137), total=150)
        with self._patch([("offset=100", page2), ("/contexts", page1)]):
            self.assertEqual(WazoClient(self.env).context_id(CONTEXTE), 137)

    def test_context_id_of_empty_name_is_none_without_call(self):
        """Sans nom de contexte, aucun appel n'est émis."""
        calls = []
        with self._patch([("/contexts", self._contexts())], calls=calls):
            self.assertIsNone(WazoClient(self.env).context_id(""))
        self.assertEqual(calls, [])


@tagged("wazo_phone", "post_install", "-at_install")
class TestContextRanges(_RangeTestBase):
    def test_ranges_are_read_from_the_context(self):
        """Les sous-plages du PBX sont rendues telles quelles, en chaînes."""
        with self._patch(
            [
                ("/ranges/user", PLAGES_REELLES["user"]),
                ("/contexts", self._contexts((CONTEXTE, 1))),
            ]
        ):
            plages = WazoClient(self.env).ranges(CONTEXTE, "user")
        self.assertEqual(
            plages,
            [
                {"start": "1000", "end": "1000"},
                {"start": "1006", "end": "1010"},
                {"start": "1012", "end": "1999"},
            ],
        )

    def test_ranges_default_to_availability_available(self):
        """Par défaut on demande la disponibilité, pas la plage brute."""
        calls = []
        with self._patch(
            [
                ("/ranges/user", PLAGES_REELLES["user"]),
                ("/contexts", self._contexts((CONTEXTE, 1))),
            ],
            calls=calls,
        ):
            WazoClient(self.env).ranges(CONTEXTE, "user")
        appel = [u for u in calls if "/ranges/" in u][0]
        self.assertIn("availability=available", appel)
        self.assertIn("/contexts/1/ranges/user", appel)

    def test_ranges_can_ask_for_the_declared_range(self):
        """``availability=all`` sert à l'appartenance à la plage."""
        calls = []
        with self._patch(
            [
                ("/ranges/group", b'{"total": 1, "items": [{"start": "2000", "end": "2099"}]}'),
                ("/contexts", self._contexts((CONTEXTE, 1))),
            ],
            calls=calls,
        ):
            plages = WazoClient(self.env).ranges(CONTEXTE, "group", availability="all")
        self.assertIn("availability=all", [u for u in calls if "/ranges/" in u][0])
        self.assertEqual(plages, [{"start": "2000", "end": "2099"}])

    def test_ranges_of_unknown_context_are_empty_without_call(self):
        """Contexte introuvable : aucune plage, et pas d'appel de plage."""
        calls = []
        with self._patch([("/contexts", self._contexts(("autre", 2)))], calls=calls):
            self.assertEqual(WazoClient(self.env).ranges(CONTEXTE, "user"), [])
        self.assertEqual([u for u in calls if "/ranges/" in u], [])

    def test_ranges_of_type_without_declared_range_are_empty(self):
        """``queue`` n'a aucune plage déclarée : liste vide, pas d'erreur."""
        with self._patch(
            [
                ("/ranges/queue", PLAGES_REELLES["queue"]),
                ("/contexts", self._contexts((CONTEXTE, 1))),
            ]
        ):
            self.assertEqual(WazoClient(self.env).ranges(CONTEXTE, "queue"), [])


@tagged("wazo_phone", "post_install", "-at_install")
class TestInRanges(_RangeTestBase):
    """Appartenance d'un numéro aux bornes rendues par l'API."""

    def test_number_inside_a_subrange_matches(self):
        self.assertTrue(
            in_ranges("1006", [{"start": "1000", "end": "1000"}, {"start": "1006", "end": "1010"}])
        )

    def test_number_in_a_gap_does_not_match(self):
        """1011 est occupé : il est absent des sous-plages disponibles."""
        self.assertFalse(
            in_ranges(
                "1011",
                [
                    {"start": "1000", "end": "1000"},
                    {"start": "1006", "end": "1010"},
                    {"start": "1012", "end": "1999"},
                ],
            )
        )

    def test_boundaries_are_included(self):
        plages = [{"start": "1000", "end": "1999"}]
        self.assertTrue(in_ranges("1000", plages))
        self.assertTrue(in_ranges("1999", plages))
        self.assertFalse(in_ranges("0999", plages))
        self.assertFalse(in_ranges("2000", plages))

    def test_empty_ranges_match_nothing(self):
        self.assertFalse(in_ranges("1000", []))

    def test_zero_padded_numbers_are_compared_numerically(self):
        """Un poste à 4 chiffres avec zéro de tête reste dans sa plage.

        C'est le cas qui justifie de ne pas comparer les chaînes telles
        quelles : la forme textuelle doit survivre, la comparaison non.
        """
        plages = [{"start": "0100", "end": "0199"}]
        self.assertTrue(in_ranges("0105", plages))
        self.assertTrue(in_ranges("0100", plages))
        self.assertFalse(in_ranges("0200", plages))
        self.assertFalse(in_ranges("0099", plages))

    def test_range_spanning_digit_widths_matches_numerically(self):
        """999-1001 : une comparaison textuelle rangerait 1000 avant 999."""
        self.assertTrue(in_ranges("1000", [{"start": "999", "end": "1001"}]))
        self.assertFalse(in_ranges("1002", [{"start": "999", "end": "1001"}]))

    def test_non_numeric_number_does_not_match(self):
        """Une saisie non numérique ne lève pas : elle ne correspond pas."""
        self.assertFalse(in_ranges("abc", [{"start": "1000", "end": "1999"}]))
        self.assertFalse(in_ranges("", [{"start": "1000", "end": "1999"}]))

    def test_incomplete_bounds_are_ignored(self):
        """Une borne manquante est ignorée plutôt que de tout faire lever."""
        self.assertFalse(in_ranges("1000", [{"start": "1000"}]))
        self.assertFalse(in_ranges("1000", [{"end": "1999"}]))
