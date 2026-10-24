# Part of the wazo_tenant Odoo module. See LICENSE for details.
"""Wazo account creation from the Odoo user.

A button on the Odoo user form creates the matching Wazo account:
auto-assigned extension within the context's free range, immediate
synchronization, direct link — the softphone answers.
"""

from odoo import models
from odoo.exceptions import UserError


class ResUsersWazoAccount(models.Model):
    _inherit = "res.users"

    def action_create_wazo_account(self):
        """Create this user's Wazo account, extension auto-assigned."""
        self.ensure_one()
        if self.wazo_user_id:
            raise UserError(
                self.env._("%s a déjà un compte Wazo (poste %s).",
                           self.name, self.wazo_user_id.extension)
            )
        User = self.env["wazo.user"].sudo()
        client = User._wazo_client()
        context = User._wazo_line_context()
        # The API only returns free ranges (availability=available): pick the
        # first number not already taken on the Odoo side.
        ranges = client.ranges(context, "user", availability="available")
        if not ranges:
            raise UserError(
                self.env._("Aucune plage de postes déclarée pour %s : "
                           "provisionnez le tenant d'abord.", context)
            )
        taken = set(User.search([]).mapped("extension"))
        poste = None
        for item in ranges:
            for number in range(int(item["start"]), int(item["end"]) + 1):
                candidate = str(number)
                if candidate not in taken:
                    poste = candidate
                    break
            if poste:
                break
        if not poste:
            raise UserError(
                self.env._("Plus de poste libre dans la plage du contexte %s.", context)
            )
        user = User.create({
            "name": self.name,
            "extension": poste,
            "partner_id": self.partner_id.id,
        })
        if user.wazo_state != "synced":
            user.action_sync_wazo()
        if user.wazo_state != "synced":
            raise UserError(
                self.env._("La synchronisation Wazo a échoué : %s",
                           user.error_message or "voir la fiche")
            )
        # The link: the field lives on the partner (delegated to res.users).
        self.partner_id.sudo().write({"wazo_user_id": user.id})
        return {
            "type": "ir.actions.act_window",
            "res_model": "wazo.user",
            "res_id": user.id,
            "view_mode": "form",
            "target": "current",
        }
