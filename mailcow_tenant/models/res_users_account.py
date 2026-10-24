# Part of the mailcow_tenant Odoo module. See LICENSE for details.
"""Mailcow mailbox creation from the Odoo user.

A button on the user form creates the matching mailbox: the user's email
address must belong to a synchronized domain.
"""

from odoo import models
from odoo.exceptions import UserError


class ResUsersMailcowAccount(models.Model):
    _inherit = "res.users"

    def action_create_mailcow_mailbox(self):
        """Create this user's Mailcow mailbox on their email address."""
        self.ensure_one()
        email = (self.email or "").strip()
        if not email or "@" not in email:
            raise UserError(
                self.env._("L'usager %s n'a pas d'adresse courriel.", self.name)
            )
        Domain = self.env["mailcow.domain"].sudo()
        Mailbox = self.env["mailcow.mailbox"].sudo()
        local_part, domain_part = email.split("@", 1)
        domain_ids = Domain.search([("name", "=", domain_part)]).ids
        if Mailbox.search_count([("local_part", "=", local_part),
                                 ("domain_id", "in", domain_ids)]):
            raise UserError(
                self.env._("La boîte %s existe déjà.", email)
            )
        domain = Domain.search([("name", "=", domain_part)], limit=1)
        if not domain:
            raise UserError(
                self.env._("Le domaine %s n'est pas synchronisé — "
                           "synchronisez les domaines d'abord.", domain_part)
            )
        mailbox = Mailbox.create({
            "local_part": local_part,
            "domain_id": domain.id,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "mailcow.mailbox",
            "res_id": mailbox.id,
            "view_mode": "form",
            "target": "current",
        }
