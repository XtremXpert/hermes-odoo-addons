"""Retain referenced audit notes when business chatter is deleted."""

from odoo import models
from odoo.exceptions import AccessError


class MailMessage(models.Model):
    _inherit = "mail.message"

    def unlink(self):
        """Supprime des messages en conservant les notes du journal.

        Une note d'audit encore référencée est réaffectée au journal
        `hermes.n1.change` avant la suppression du message d'origine ; une note du
        journal lui-même reste immuable.

        Returns:
            bool: résultat de la suppression des messages restants.

        Raises:
            odoo.exceptions.AccessError: suppression d'une note du journal Hermes N1.
        """
        if not self:
            return super().unlink()
        # Preserve the normal caller's access checks before touching audit data.
        self.check_access("unlink")
        audits = (
            self.env["hermes.n1.change"].sudo().search([("chatter_message_id", "in", self.ids)])
        )
        protected = self.browse(audits.mapped("chatter_message_id").ids)
        for audit in audits:
            note = audit.chatter_message_id
            if note.model == audit._name and note.res_id == audit.id:
                raise AccessError(  # pylint: disable=no-raise-unlink
                    self.env._("La note du journal Hermes N1 est conservée de façon immuable.")
                )
            # Only the audit's own note is reparented, never the business record.
            # Its id/body and the immutable audit reference remain unchanged.
            # This also handles child records deleted by a parent ORM cascade.
            note.sudo().write({"model": audit._name, "res_id": audit.id})
        return super(MailMessage, self - protected).unlink()
