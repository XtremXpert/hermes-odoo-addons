# Copyright 2026 XtremXpert
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

"""A request for a document, tracked from the ask to the validated upload.

The lifecycle: an asker requests a document from a colleague (with a
deadline and a target directory), the colleague uploads the file from
the request itself, the asker validates. The file then lives its normal
DMS life — the request is the workflow around it, never a copy.
"""

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError


class DmsFileRequest(models.Model):
    _name = "dms.file.request"
    _description = "DMS Document Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "deadline, id desc"

    name = fields.Char(required=True, tracking=True)
    description = fields.Html()
    # The directory where the uploaded file will be stored.
    directory_id = fields.Many2one(
        "dms.directory", string="Répertoire cible", required=True, tracking=True
    )
    # The colleague asked for the document.
    requested_to_id = fields.Many2one(
        "res.users", string="Demandé à", required=True, tracking=True,
        default=lambda self: self.env.user,
        domain=lambda self: [("groups_id", "in", self.env.ref("dms.group_dms_user").id)],
    )
    requested_by_id = fields.Many2one(
        "res.users", string="Demandé par", readonly=True,
        default=lambda self: self.env.user,
    )
    deadline = fields.Date(tracking=True)
    file_id = fields.Many2one(
        "dms.file", string="Fichier déposé", readonly=True, tracking=True
    )
    state = fields.Selection(
        [
            ("submitted", "Demandé"),
            ("uploaded", "Déposé — à valider"),
            ("done", "Validé"),
            ("refused", "Refusé"),
            ("cancelled", "Annulé"),
        ],
        default="submitted",
        required=True,
        tracking=True,
    )

    def action_upload(self):
        """Open the file creation form, bound to this request.

        The directory and the request link are preset; saving the file
        moves the request to 'uploaded' (see dms.file create hook)."""
        self.ensure_one()
        if self.state not in {"submitted", "refused"}:
            raise UserError("Cette demande n'attend plus de document.")
        return {
            "type": "ir.actions.act_window",
            "name": "Déposer — %s" % self.name,
            "res_model": "dms.file",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_directory_id": self.directory_id.id,
                "default_request_id": self.id,
            },
        }

    def action_validate(self):
        for request in self:
            if request.state != "uploaded" or not request.file_id:
                raise UserError("Aucun document déposé à valider.")
            request.state = "done"

    def action_refuse(self):
        for request in self:
            if request.state not in {"uploaded", "submitted"}:
                raise UserError("Cette demande ne peut plus être refusée.")
            request.state = "refused"

    def action_cancel(self):
        for request in self:
            if request.state == "done":
                raise UserError("Une demande validée ne s'annule pas.")
            request.state = "cancelled"

    def action_reopen(self):
        """A refused or cancelled request can be asked again."""
        for request in self:
            if request.state not in {"refused", "cancelled"}:
                raise UserError("Seule une demande refusée ou annulée se relance.")
            request.file_id = False
            request.state = "submitted"

    @api.model_create_multi
    def create(self, vals_list):
        requests = super().create(vals_list)
        # The target gets an activity with the deadline: the request
        # itself is the tracking, the activity is the reminder.
        for request in requests:
            if request.requested_to_id and request.requested_to_id != request.requested_by_id:
                request.activity_schedule(
                    "mail.mail_activity_data_todo",
                    date_deadline=request.deadline,
                    summary="Document demandé : %s" % request.name,
                    user_id=request.requested_to_id.id,
                )
        return requests

    def write(self, vals):
        res = super().write(vals)
        # Keep the reminder in sync when the deadline moves.
        if "deadline" in vals:
            for request in self:
                target = request.requested_to_id
                for activity in request.activity_ids.filtered(
                    lambda a, _target=target: a.user_id == _target
                ):
                    activity.date_deadline = request.deadline
        return res
