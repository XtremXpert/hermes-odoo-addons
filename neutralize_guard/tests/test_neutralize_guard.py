from unittest.mock import patch

from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestNeutralizeGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.icp = cls.env["ir.config_parameter"].sudo()
        cls.cron = cls.env["ir.cron"].search([], limit=1)
        if not cls.cron:
            # Une base sans aucun cron ne prouve rien : on en crée un minimal.
            cls.cron = cls.env["ir.cron"].create(
                {
                    "name": "neutralize_guard test",
                    "state": "code",
                    "code": "pass",
                    "interval_number": 1,
                    "interval_type": "days",
                }
            )

    def setUp(self):
        super().setUp()
        self.addCleanup(self.icp.set_bool, "database.is_neutralized", False)

    def test_flags_the_neutralized_database(self):
        self.icp.set_bool("database.is_neutralized", True)
        self.assertTrue(self.cron._is_neutralized())
        self.icp.set_bool("database.is_neutralized", False)
        self.assertFalse(self.cron._is_neutralized())

    def test_callback_refuses_on_a_neutralized_database(self):
        self.icp.set_bool("database.is_neutralized", True)
        action = self.cron.ir_actions_server_id
        with patch.object(type(action), "run") as run:
            result = self.cron._callback(self.cron.name, action.id)
        self.assertIs(result, False)
        run.assert_not_called()

    def test_callback_delegates_on_a_normal_database(self):
        self.icp.set_bool("database.is_neutralized", False)
        action = self.cron.ir_actions_server_id
        # `_callback` n'est pas défini par la première classe parente : la chaîne
        # passe par des héritages (mail, par exemple) qui n'en déclarent rien, et
        # `patch.object` exige l'attribut SUR la classe visée, pas hérité. On
        # cherche donc celle qui le déclare réellement, quel que soit le nombre
        # d'héritages intermédiaires.
        parent = next(
            classe for classe in type(self.cron).__mro__[1:] if "_callback" in classe.__dict__
        )
        with patch.object(parent, "_callback") as delegated:
            self.cron._callback(self.cron.name, action.id)
        delegated.assert_called_once_with(self.cron.name, action.id)
