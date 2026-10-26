# Part of the mailcow_tenant Odoo module. See LICENSE for details.
"""Base module update — tolérance aux langues vides.

Le wizard ``base.module.update`` itère les langues des membres de
``base.group_system`` : un usager sans langue (``lang = False``) rend un
booléen que ``get_base_langs`` essaie de découper — crash
``'bool' object has no attribute 'split'`` à chaque « Mettre à jour ».
"""

from odoo import models


class BaseModuleUpdate(models.TransientModel):
    _inherit = "base.module.update"

    def update_module(self):
        # Rejoue le corps d'Odoo mais en ignorant les langues vides.
        self.ensure_one()
        updated, added = self.env["ir.module.module"].update_list()
        langs = [
            lang for lang in self.env.ref("base.group_system").all_user_ids.mapped("lang") if lang
        ]
        self.env["ir.module.module"]._load_non_installed_modules_manifest_terms(langs)
        self.write({"updated": updated, "added": added, "state": "done"})
