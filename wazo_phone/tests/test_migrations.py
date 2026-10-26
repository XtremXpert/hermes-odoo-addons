# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Reprise des membres de groupes d'appel (migration 20.0.3.0.0).

La table ``wazo_ring_group_wazo_user_rel`` n'existe que sur les bases
venues de l'ancien schéma : le test la recrée, la sème, joue ``migrate``
et vérifie que les membres arrivent avec la priorité par défaut — et
qu'un second passage n'en duplique aucun (idempotence).
"""

import importlib.util
from pathlib import Path

from odoo.tests.common import TransactionCase

ANCIENNE_TABLE = "wazo_ring_group_wazo_user_rel"
SCRIPT = Path(__file__).resolve().parent.parent / "migrations" / "20.0.3.0.0" / "post-migrate.py"


def _charger_migrate():
    """Le dossier 20.0.3.0.0 n'est pas importable : charger le fichier."""
    spec = importlib.util.spec_from_file_location("post_migrate_2003", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.migrate


class TestMigrationMembres(TransactionCase):
    """La reprise des membres est complète et idempotente."""

    def setUp(self):
        super().setUp()
        self.env.cr.execute("DROP TABLE IF EXISTS %s" % ANCIENNE_TABLE)
        self.env.cr.execute("CREATE TABLE %s (group_id int4, user_id int4)" % ANCIENNE_TABLE)
        self.migrate = _charger_migrate()

    def tearDown(self):
        self.env.cr.execute("DROP TABLE IF EXISTS %s" % ANCIENNE_TABLE)
        super().tearDown()

    def _usager(self, nom):
        return self.env["wazo.user"].create({"name": nom}).id

    def _groupe(self):
        return self.env["wazo.ring.group"].create({"name": "Groupe test"})

    def _seed(self, group_id, user_ids):
        for user_id in user_ids:
            self.env.cr.execute(
                "INSERT INTO %s (group_id, user_id) VALUES (%%s, %%s)" % ANCIENNE_TABLE,
                (group_id, user_id),
            )

    def test_la_reprise_copie_les_membres(self):
        """Chaque lien de l'ancienne table devient un membre repris."""
        groupe = self._groupe()
        u1, u2 = self._usager("Alice"), self._usager("Bob")
        self._seed(groupe.id, [u1, u2])
        self.migrate(self.env.cr, "20.0.2.0.0")
        membres = self.env["wazo.ring.group.member"].search([("group_id", "=", groupe.id)])
        self.assertEqual(sorted(membres.mapped("user_id").ids), sorted([u1, u2]))
        # La priorité par défaut du modèle est reprise — seul l'ensemble importe.
        self.assertEqual(set(membres.mapped("priority")), {10})

    def test_un_second_passage_ne_duplique_pas(self):
        """Idempotence : la clause NOT EXISTS protège les membres déjà repris."""
        groupe = self._groupe()
        self._seed(groupe.id, [self._usager("Alice")])
        self.migrate(self.env.cr, "20.0.2.0.0")
        self.migrate(self.env.cr, "20.0.2.0.0")
        self.assertEqual(
            self.env["wazo.ring.group.member"].search_count([("group_id", "=", groupe.id)]),
            1,
        )

    def test_une_base_neuve_n_est_pas_touchee(self):
        """Sans version (installation fraîche), la migration ne fait rien."""
        groupe = self._groupe()
        self._seed(groupe.id, [self._usager("Alice")])
        self.migrate(self.env.cr, None)
        self.assertFalse(self.env["wazo.ring.group.member"].search([("group_id", "=", groupe.id)]))

    def test_sans_ancienne_table_rien_ne_casse(self):
        """La table absente (jamais eu le vieux schéma) est tolérée."""
        self.env.cr.execute("DROP TABLE IF EXISTS %s" % ANCIENNE_TABLE)
        self.migrate(self.env.cr, "20.0.2.0.0")  # ne doit pas lever
