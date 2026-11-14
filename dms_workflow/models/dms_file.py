# Copyright 2026 XtremXpert
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

"""Link between an uploaded file and the request it answers."""

from odoo import api
from odoo import fields
from odoo import models


class DmsFile(models.Model):
    _inherit = "dms.file"

    request_id = fields.Many2one(
        "dms.file.request",
        string="Demande de document",
        readonly=True,
        index=True,
        copy=False,
    )

    def _update_request_on_upload(self):
        """Called after creation: the request moves to 'uploaded'.

        Only the first file wins: a second upload on the same request is
        a normal file, the request keeps its first answer."""
        for dms_file in self:
            request = dms_file.request_id
            if request and request.state in {"submitted", "refused"}:
                request.sudo().write({"file_id": dms_file.id, "state": "uploaded"})

    @api.model_create_multi
    def create(self, vals_list):
        files = super().create(vals_list)
        files._update_request_on_upload()
        return files
