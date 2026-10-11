from odoo.modules.neutralize import get_neutralization_queries
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestHermesN3Access(TransactionCase):
    def setUp(self):
        super().setUp()
        self.user = self.env.ref("hermes_n3_access.user_hermes_n3")
        self.human = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Humain",
                    "login": "n3_access_human",
                    "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
                }
            )
        )

    def test_api_account_is_internal_but_never_admin(self):
        self.assertTrue(self.user._is_internal())
        self.assertTrue(self.user.has_group("base.group_partner_manager"))
        self.assertFalse(self.user.has_group("base.group_system"))
        self.assertFalse(self.user.has_group("base.group_erp_manager"))

    def test_neutralize_drops_n3_keys_and_disables_only_n3(self):
        keys = self.env["res.users.apikeys"].sudo()
        keys.with_user(self.user).sudo()._generate(None, "n3 key", False)
        keys.with_user(self.human).sudo()._generate(None, "human key", False)
        self.env.flush_all()
        for query in get_neutralization_queries(["hermes_n3_access"]):
            self.env.cr.execute(query)
        self.env.invalidate_all()
        self.assertFalse(self.user.active)
        self.assertFalse(keys.search([("user_id", "=", self.user.id)]))
        self.assertTrue(self.human.active)
        self.assertTrue(keys.search([("user_id", "=", self.human.id)]))
