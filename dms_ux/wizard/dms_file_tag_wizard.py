# Copyright 2026 XtremXpert
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

"""Tag many files at once."""

from odoo import fields
from odoo import models
from odoo.exceptions import UserError


class DmsFileTagWizard(models.TransientModel):
    _name = "dms.file.tag.wizard"
    _description = "DMS Tag Files Wizard"

    file_ids = fields.Many2many("dms.file", string="Fichiers")
    tag_ids = fields.Many2many("dms.tag", string="Étiquettes à ajouter")

    def action_tag(self):
        self.ensure_one()
        if not self.file_ids:
            raise UserError("Aucun fichier sélectionné.")
        if not self.tag_ids:
            raise UserError("Aucune étiquette à ajouter.")
        for dms_file in self.file_ids:
            dms_file.tag_ids = [(4, tag.id) for tag in self.tag_ids]
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": "%d étiquette(s) ajoutée(s) à %d fichier(s)."
                           % (len(self.tag_ids), len(self.file_ids)),
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
