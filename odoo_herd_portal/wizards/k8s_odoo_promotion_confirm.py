from odoo import _
from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError


class K8sOdooPromotionConfirm(models.TransientModel):
    """Backend twin of the portal confirmation: the same private checks of
    k8s.odoo.promotion (human approver, authenticator app or e-mailed code)."""

    _name = "k8s.odoo.promotion.confirm"
    _description = "Confirm a promotion to production"

    promotion_id = fields.Many2one(
        "k8s.odoo.promotion", required=True, readonly=True, ondelete="cascade"
    )
    method = fields.Selection(
        [("totp", "Authenticator app"), ("email", "Code by e-mail")],
        compute="_compute_method",
    )
    code = fields.Char()
    message = fields.Char(readonly=True)
    error = fields.Char(readonly=True)
    # Summary of what is being confirmed, read from the promotion.
    production_id = fields.Many2one(related="promotion_id.production_id")
    staging_id = fields.Many2one(related="promotion_id.staging_id")
    image = fields.Char(related="promotion_id.image")
    modules = fields.Char(related="promotion_id.modules")
    modules_install = fields.Char(related="promotion_id.modules_install")
    scheduled_at = fields.Datetime(related="promotion_id.scheduled_at")

    @api.depends("promotion_id")
    def _compute_method(self):
        for wizard in self:
            wizard.method = wizard.promotion_id._herd_confirm_method(self.env.user) or False

    def _reopen(self, message=False, error=False):
        self.write({"code": False, "message": message, "error": error})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "name": _("Confirm %s", self.promotion_id.name),
        }

    def action_send_code(self):
        self.ensure_one()
        # sudo record as in the portal; the checks use the real user passed in.
        self.promotion_id.sudo()._herd_send_code(self.env.user)
        return self._reopen(_("A code was sent to %s.", self.env.user.email))

    def action_confirm(self):
        self.ensure_one()
        if not self.code:
            raise UserError(_("Enter the code."))
        # A wrong code returns instead of raising: the attempt stays counted.
        if not self.promotion_id.sudo()._herd_confirm(self.env.user, self.code):
            return self._reopen(error=_("Wrong code."))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _("Promotion %s confirmed.", self.promotion_id.name),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
