# Copyright 2026 XtremXpert
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

"""One line of a device sync scope: a directory, a direction, exclusions."""

from odoo import fields
from odoo import models


class DmsSyncScopeLine(models.Model):
    _name = "dms.sync.scope.line"
    _description = "DMS Sync Scope Line"

    device_id = fields.Many2one(
        "dms.sync.device", string="Appareil", required=True, ondelete="cascade",
        index=True, readonly=True,
    )
    directory_id = fields.Many2one(
        "dms.directory", string="Répertoire", required=True, ondelete="cascade",
        index=True, readonly=True,
    )
    enabled = fields.Boolean(string="Synchronisé", default=True)
    mode = fields.Selection(
        [("two_way", "Bidirectionnel"), ("read_down", "Descendant seul")],
        string="Sens", default="two_way", required=True,
    )
    # Comma-separated glob patterns: *.tmp, *.iso, ~$*
    exclude_patterns = fields.Char(
        string="Exclusions", help="Motifs séparés par des virgules : *.tmp, *.iso"
    )
