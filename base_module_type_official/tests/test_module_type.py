from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestModuleType(TransactionCase):
    def _set_type(self, module, value):
        self.env.cr.execute(
            "UPDATE ir_module_module SET module_type = %s WHERE id = %s",
            (value, module.id),
        )
        module.invalidate_recordset(["module_type"])

    def test_empty_type_becomes_official_and_industries_is_kept(self):
        Module = self.env["ir.module.module"]
        empty, industry = Module.search([("state", "=", "uninstalled")], limit=2)
        self._set_type(empty, None)
        self._set_type(industry, "industries")
        self.assertFalse(empty.module_type)

        self.assertGreaterEqual(Module._fill_missing_module_type(), 1)

        self.assertEqual(empty.module_type, "official")
        self.assertEqual(industry.module_type, "industries")
        self.assertFalse(Module.search_count([("module_type", "=", False)]))

    def test_nothing_to_do_returns_zero(self):
        Module = self.env["ir.module.module"]
        Module._fill_missing_module_type()
        self.assertEqual(Module._fill_missing_module_type(), 0)

    def test_registry_hook_fills_the_type(self):
        Module = self.env["ir.module.module"]
        module = Module.search([("state", "=", "uninstalled")], limit=1)
        self._set_type(module, None)
        Module._register_hook()
        self.assertEqual(module.module_type, "official")
