# Copyright 2026 XtremXpert
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

"""Move many files to another directory in one action."""

from odoo import fields
from odoo import models
from odoo.exceptions import UserError


class DmsFileMoveWizard(models.TransientModel):
    _name = "dms.file.move.wizard"
    _description = "DMS Move Files Wizard"

    file_ids = fields.Many2many("dms.file", string="Fichiers")
    directory_id = fields.Many2one(
        "dms.directory", string="Répertoire de destination", required=True
    )

    def action_move(self):
        self.ensure_one()
        files = self.file_ids
        if not files:
            raise UserError("Aucun fichier sélectionné.")
        # Same-directory moves are a no-op, skipped silently.
        to_move = files.filtered(lambda f: f.directory_id != self.directory_id)
        to_move.write({"directory_id": self.directory_id.id})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": "%d fichier(s) déplacé(s) vers %s."
                           % (len(to_move), self.directory_id.name),
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
