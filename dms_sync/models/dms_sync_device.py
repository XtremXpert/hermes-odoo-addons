# Copyright 2026 XtremXpert
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

"""Per-device sync scope: what the desktop client may synchronize.

The scope is an Odoo record, not a client-side setting: the client reads
it (and may edit it through dedicated methods that write back here),
but the file endpoints below only ever serve what the scope allows.
Access groups still apply underneath — the scope is an intersection,
never an elevation.
"""

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import AccessError
from odoo.exceptions import ValidationError


class DmsSyncDevice(models.Model):
    _name = "dms.sync.device"
    _description = "DMS Sync Device"
    _order = "name"

    name = fields.Char(required=True)
    user_id = fields.Many2one(
        "res.users", string="Utilisateur", required=True, readonly=True,
        default=lambda self: self.env.user, index=True,
    )
    hostname = fields.Char(string="Nom de l'hôte")
    paused = fields.Boolean(string="Suspendu", default=False)
    last_seen = fields.Datetime(readonly=True)
    scope_line_ids = fields.One2many(
        "dms.sync.scope.line", "device_id", string="Périmètre"
    )
    scope_directory_count = fields.Integer(compute="_compute_scope_directory_count")

    _user_name_uniq = models.Constraint(
        "unique(user_id, name)",
        "Cet appareil existe déjà pour cet utilisateur.",
    )

    def _compute_scope_directory_count(self):
        for device in self:
            device.scope_directory_count = len(
                device.scope_line_ids.filtered("enabled")
            )

    # ------------------------------------------------------------------
    # Client API — called over JSON-RPC by the desktop client.
    # ------------------------------------------------------------------

    def _check_own_device(self):
        """Every client call is bound to a device owned by the caller."""
        for device in self:
            if device.user_id != self.env.user:
                raise AccessError("Cet appareil n'appartient pas à cet utilisateur.")

    def action_get_scope(self):
        """The sync profile: enabled lines with directory paths and modes.

        The client calls this at startup and before every cycle: a change
        made in Odoo propagates on the next cycle."""
        self._check_own_device()
        self.write({"last_seen": fields.Datetime.now()})
        return {
            "device": self.name,
            "paused": self.paused,
            "scope": [
                {
                    "directory_id": line.directory_id.id,
                    "directory_name": line.directory_id.name,
                    "enabled": line.enabled,
                    "mode": line.mode,
                    "exclude": line.exclude_patterns or "",
                }
                for line in self.scope_line_ids
            ],
        }

    def action_set_scope(self, lines):
        """Edit the scope from the client: checkboxes write back to Odoo.

        ``lines`` is a list of dicts with directory_id, enabled and mode —
        the client may only change its own lines, never create arbitrary
        ones: the directory must already appear in the device scope."""
        self._check_own_device()
        if not isinstance(lines, list):
            raise ValidationError("Périmètre invalide.")
        known = {line.directory_id.id: line for line in self.scope_line_ids}
        for entry in lines:
            line = known.get(entry.get("directory_id"))
            if not line:
                raise AccessError("Répertoire hors du périmètre de l'appareil.")
            if entry.get("mode") not in ("two_way", "read_down"):
                raise ValidationError("Mode de synchronisation invalide.")
            line.write({
                "enabled": bool(entry.get("enabled")),
                "mode": entry.get("mode"),
            })
        return True

    @api.model
    def action_available_directories(self):
        """The tree the client shows in 'choose what to sync'.

        Access groups apply: only directories readable by the caller are
        offered — enforced here, not trusted from the client."""
        Directory = self.env["dms.directory"].with_context(active_test=False)
        return [
            {
                "id": directory.id,
                "name": directory.name,
                "parent_id": directory.parent_id.id or False,
            }
            for directory in Directory.search([])
        ]

    def _scope_directories(self):
        """Directories this device may synchronize — the server-side gate."""
        self.ensure_one()
        return self.scope_line_ids.filtered("enabled").mapped("directory_id")

    def _check_file_in_scope(self, dms_file):
        """File endpoints refuse anything outside the enabled scope."""
        self.ensure_one()
        if dms_file.directory_id not in self._scope_directories():
            raise AccessError("Fichier hors du périmètre de synchronisation.")

    def action_list_sync_files(self):
        """Checksums of every file in scope: the client's change detection.

        The SHA1 on dms.file is the sync truth — the client compares its
        local checksums against this list and pulls or pushes the diffs."""
        self._check_own_device()
        files = self.env["dms.file"].search([
            ("directory_id", "in", self._scope_directories().ids),
        ])
        return [
            {
                "id": dms_file.id,
                "name": dms_file.name,
                "directory_id": dms_file.directory_id.id,
                "checksum": dms_file.checksum or "",
                "write_date": fields.Datetime.to_string(dms_file.write_date),
                "size": dms_file.size or 0,
            }
            for dms_file in files
        ]

    def action_get_file(self, file_id):
        """Download one in-scope file (the sync engine's pull path)."""
        self._check_own_device()
        dms_file = self.env["dms.file"].browse(file_id).exists()
        if not dms_file:
            raise ValidationError("Fichier introuvable.")
        self._check_file_in_scope(dms_file)
        # Read through the caller: access groups still apply on top of scope.
        dms_file = dms_file.with_user(self.env.user)
        # Binary fields return a lazy BinaryValue — force base64 while the
        # cursor is open, the proxy cannot cross JSON-RPC.
        content = dms_file.content
        return {
            "name": dms_file.name,
            "content": content.to_base64() if content else "",
        }

    def action_put_file(self, directory_id, name, content_b64, checksum):
        """Upload one in-scope file (the sync engine's push path).

        Overwriting existing content goes through dms.file's normal write
        path — with dms_versions installed, the replaced content is
        archived first, so a client push can never destroy history."""
        self._check_own_device()
        directory = self.env["dms.directory"].browse(directory_id).exists()
        if not directory or directory not in self._scope_directories():
            raise AccessError("Répertoire hors du périmètre de synchronisation.")
        existing = self.env["dms.file"].search([
            ("directory_id", "=", directory_id), ("name", "=", name),
        ], limit=1)
        if existing:
            existing.with_user(self.env.user).write({"content": content_b64})
            return {"id": existing.id, "checksum": existing.checksum or ""}
        dms_file = self.env["dms.file"].with_user(self.env.user).create({
            "name": name,
            "directory_id": directory_id,
            "content": content_b64,
        })
        return {"id": dms_file.id, "checksum": dms_file.checksum or ""}
