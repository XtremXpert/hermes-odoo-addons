# Copyright 2026 XtremXpert
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

"""Immutable snapshots of a DMS file content.

A version is created automatically whenever the content of a dms.file is
about to change: the previous bytes, checksum and metadata are archived
before the new content lands. Versions are never edited in place —
restoring one writes it back through the normal file write path, which
archives the current content as a new version first. The chain is
therefore never broken by a restore.
"""

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import AccessError


class DmsFileVersion(models.Model):
    _name = "dms.file.version"
    _description = "DMS File Version"
    _order = "create_date desc, id desc"
    _rec_name = "display_label"

    file_id = fields.Many2one(
        "dms.file",
        string="File",
        required=True,
        readonly=True,
        ondelete="cascade",
        index=True,
    )
    # Snapshot of the file metadata at the time the version was archived:
    # the file may be renamed afterwards, the version keeps what it was.
    name = fields.Char(readonly=True)
    extension = fields.Char(readonly=True)
    mimetype = fields.Char(string="Type", readonly=True)
    checksum = fields.Char(readonly=True, index=True)
    size = fields.Float(readonly=True)
    content = fields.Binary(attachment=True, readonly=True, prefetch=False)
    # 'update': the content was replaced. 'restore': an older version was
    # written back, archiving what was there just before the restore.
    origin = fields.Selection(
        [("update", "Remplacement"), ("restore", "Avant restauration")],
        readonly=True,
    )
    display_label = fields.Char(compute="_compute_display_label")

    _file_checksum_uniq = models.Constraint(
        "unique(file_id, checksum)",
        "Cette version existe déjà pour ce fichier.",
    )

    @api.depends("name", "create_date")
    def _compute_display_label(self):
        for version in self:
            when = fields.Datetime.context_timestamp(
                version, version.create_date or fields.Datetime.now()
            )
            version.display_label = "%s — %s" % (
                version.name or version.file_id.name,
                when.strftime("%d/%m/%Y %H:%M"),
            )

    def action_restore(self):
        """Write this version's bytes back into the file.

        Permissions go through the file itself: only someone who could
        edit the file may restore a version of it."""
        self.ensure_one()
        dms_file = self.file_id
        dms_file.check_access("write")
        # Guard against restoring a version into a file whose storage
        # configuration changed under our feet: the checksum of the
        # archived bytes is compared to the file's current one.
        if self.checksum and self.checksum == dms_file.checksum:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "message": "Cette version est déjà le contenu actuel.",
                    "type": "info",
                },
            }
        # The normal write path archives the current content first
        # (see dms.file.write override), so the chain stays complete.
        # bytes(): freeze the lazy attachment proxy before the write path
        # touches the file's own attachment.
        dms_file.with_context(dms_version_restore=True).sudo().content = (
            bytes(self.content) if self.content else False
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": "Version restaurée — le contenu précédent est archivé.",
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def unlink(self):
        # Versions are audit records: only a DMS manager may purge them,
        # and the restore flow never needs to delete anything.
        if not self.env.user.has_group("dms.group_dms_manager"):
            raise AccessError("Seul un gestionnaire DMS peut supprimer des versions.")
        return super().unlink()
