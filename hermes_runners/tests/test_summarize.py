# Part of the hermes_runners Odoo module. See LICENSE for details.
"""L'agrégation des pools, testée sans cluster ni réseau.

C'est la seule partie du module qui décide quelque chose : le reste lit des
objets et les transmet. Elle mérite donc des tests qui ne demandent ni
Kubernetes ni jeton.
"""

from odoo.tests import TransactionCase
from odoo.tests import tagged

from ..models.runners import summarize_pools


@tagged("post_install", "-at_install")
class TestSummarizePools(TransactionCase):
    def test_occupation_et_saturation(self):
        """Vérifie le calcul d'occupation, de places libres et de saturation par pool."""
        pools = [
            {"name": "arc-a", "min": 1, "max": 2, "repo": "org/a"},
            {"name": "arc-b", "min": 0, "max": 3, "repo": "org/b"},
        ]
        runners = [
            {"pool": "arc-a"},
            {"pool": "arc-a"},
            {"pool": "arc-b"},
        ]
        resume = {p["name"]: p for p in summarize_pools(pools, runners)}
        self.assertEqual(resume["arc-a"]["running"], 2)
        self.assertEqual(resume["arc-a"]["free"], 0)
        self.assertTrue(resume["arc-a"]["saturated"])
        self.assertEqual(resume["arc-b"]["running"], 1)
        self.assertEqual(resume["arc-b"]["free"], 2)
        self.assertFalse(resume["arc-b"]["saturated"])

    def test_pool_en_pause(self):
        """maxRunners = 0 : le pool est en pause, pas « sature ».

        Confondre les deux ferait afficher une alerte rouge sur un pool
        volontairement éteint.
        """
        resume = summarize_pools([{"name": "arc-off", "min": 0, "max": 0}], [])
        self.assertTrue(resume[0]["paused"])
        self.assertFalse(resume[0]["saturated"])
        self.assertEqual(resume[0]["free"], 0)

    def test_runner_hors_pool_connu(self):
        """Un runner dont le pool a disparu ne casse pas le résumé."""
        resume = summarize_pools(
            [{"name": "arc-a", "min": 0, "max": 1}],
            [{"pool": "arc-disparu"}],
        )
        self.assertEqual(resume[0]["running"], 0)
        self.assertEqual(resume[0]["free"], 1)

    def test_tri_stable(self):
        """Vérifie que les pools sont triés par nom."""
        pools = [{"name": "z"}, {"name": "a"}, {"name": "m"}]
        self.assertEqual([p["name"] for p in summarize_pools(pools, [])], ["a", "m", "z"])
