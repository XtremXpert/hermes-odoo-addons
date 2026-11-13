from unittest.mock import patch

from odoo.tests import TransactionCase
from odoo.tests import tagged

from ..models.ir_cron import IrCron


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
        # `_callback` n'est pas défini par le parent immédiat : mail, event et
        # d'autres surchargent ir.cron sans le redéfinir, donc __mro__[1] n'a
        # pas l'attribut et patch.object lève AttributeError. On vise la
        # classe que super() atteint réellement depuis notre surcharge.
        mro = type(self.cron).__mro__
        after_ours = mro[mro.index(IrCron) + 1 :]
        parent = next(klass for klass in after_ours if "_callback" in vars(klass))
        with patch.object(parent, "_callback") as delegated:
            self.cron._callback(self.cron.name, action.id)
        delegated.assert_called_once_with(self.cron.name, action.id)
