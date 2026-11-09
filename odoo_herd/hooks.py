from openupgradelib import openupgrade


def post_remove_old_module(env):
    """Hook post-init : désinstalle `odoo_herd` s'il est encore installé.

    Valide ensuite la transaction pour que la désinstallation soit effective.
    """
    if openupgrade.is_module_installed(env.cr, "odoo_herd"):
        env["ir.module.module"].search([("name", "=", "odoo_herd")]).button_uninstall()
        env.cr.commit()
