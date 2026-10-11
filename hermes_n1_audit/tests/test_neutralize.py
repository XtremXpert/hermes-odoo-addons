from odoo.modules.neutralize import get_installed_modules
from odoo.modules.neutralize import get_neutralization_queries
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestNeutralize(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env["res.users"].with_context(no_reset_password=True)
        cls.agent = Users.create(
            {
                "name": "Neutralize test agent",
                "login": "n1_neutralize_agent",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("hermes_n1_audit.group_agent").id,
                        ],
                    )
                ],
            }
        )
        cls.human = Users.create(
            {
                "name": "Neutralize test human",
                "login": "n1_neutralize_human",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        ApiKeys = cls.env["res.users.apikeys"].sudo()
        ApiKeys.with_user(cls.agent).sudo()._generate(None, "agent key", False)
        ApiKeys.with_user(cls.human).sudo()._generate(None, "human key", False)

    def _neutralize(self):
        self.env.flush_all()
        modules = get_installed_modules(self.env.cr)
        self.assertIn("hermes_n1_audit", modules)
        queries = list(get_neutralization_queries(["hermes_n1_audit"]))
        self.assertEqual(len(queries), 1)
        self.env.cr.execute(queries[0])
        self.env.invalidate_all()

    def test_neutralize_deactivates_agents_and_drops_their_keys(self):
        self._neutralize()
        self.assertFalse(self.agent.active)
        self.assertFalse(
            self.env["res.users.apikeys"].sudo().search([("user_id", "=", self.agent.id)])
        )

    def test_neutralize_leaves_humans_alone(self):
        self._neutralize()
        self.assertTrue(self.human.active)
        self.assertTrue(
            self.env["res.users.apikeys"].sudo().search([("user_id", "=", self.human.id)])
        )
