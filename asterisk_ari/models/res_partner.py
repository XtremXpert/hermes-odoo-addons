# Part of the asterisk_ari Odoo module. See LICENSE for details.
"""Bouton click-to-call sur la fiche partenaire."""

from odoo import models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    def action_click_to_call(self):
        """Crée un appel click-to-call vers le numéro du partenaire."""
        self.ensure_one()
        phone = (self.phone or "").strip()
        if not phone:
            raise UserError(self.env._("Aucun numéro de téléphone pour %s.", self.name or ""))
        call = self.env["asterisk.call"].create(
            {
                "partner_id": self.id,
                "phone": phone,
            }
        )
        call.action_originate()
        return call
