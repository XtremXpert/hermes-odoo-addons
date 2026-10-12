from odoo.modules.neutralize import get_neutralization_queries
from odoo.tests import TransactionCase
from odoo.tests import new_test_user
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestHerdNeutralize(TransactionCase):
    """A neutralized copy keeps the CI account and its API key: they must not
    work there, and the clusters must be off."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ci = new_test_user(
            cls.env,
            login="herd_ci_neutralize",
            groups="base.group_user,odoo_herd_portal.group_staging_operator",
        )
        cls.human = new_test_user(cls.env, login="herd_human_neutralize", groups="base.group_user")
        ApiKeys = cls.env["res.users.apikeys"].sudo()
        ApiKeys.with_user(cls.ci).sudo()._generate(None, "ci key", False)
        ApiKeys.with_user(cls.human).sudo()._generate(None, "human key", False)

    def _neutralize(self):
        self.env.flush_all()
        for query in get_neutralization_queries(["odoo_herd_portal"]):
            self.env.cr.execute(query)
        self.env.invalidate_all()

    def test_neutralize_disables_staging_operators_and_their_keys(self):
        self._neutralize()
        self.assertFalse(self.ci.active)
        Keys = self.env["res.users.apikeys"].sudo()
        self.assertFalse(Keys.search([("user_id", "=", self.ci.id)]))
        self.assertTrue(self.human.active)
        self.assertTrue(Keys.search([("user_id", "=", self.human.id)]))
