# Part of the imap_client Odoo module. See LICENSE for details.
"""Assistant de réponse — envoie par le serveur sortant d'Odoo (Mailcow).

Le message part par ``mail.mail`` : les en-têtes ``In-Reply-To`` et
``References`` portent le Message-ID du courriel d'origine — le fil reste
complet côté destinataire et dans le dossier Envoyés du compte IMAP.
"""

from odoo import fields
from odoo import models
from odoo.exceptions import AccessError


class ImapReply(models.TransientModel):
    _name = "imap.reply"
    _inherit = ["mail.thread"]
    _description = "Réponse à un courriel IMAP"

    message_id = fields.Many2one(
        "imap.message", string="Message d'origine", required=True, readonly=True
    )
    to_addr = fields.Char(string="À", required=True)
    subject = fields.Char(string="Sujet", required=True)
    body = fields.Html(string="Message", required=True)

    def _exiger(self):
        if self.env.su or self.env.user.has_group("imap_client.group_imap_user"):
            return
        raise AccessError(self.env._("Envoi IMAP réservé aux usagers."))

    def action_envoyer(self):
        """Envoyer la réponse par le serveur sortant d'Odoo."""
        self._exiger()
        self.ensure_one()
        origin = self.message_id
        corps = self.env["mail.mail"].sudo().create(
            {
                "subject": self.subject,
                "email_to": self.to_addr,
                "email_from": self.env.user.email or self.env.user.login,
                "body_html": self.body,
                "headers": {
                    "In-Reply-To": origin.message_id or "",
                    "References": origin.message_id or "",
                },
            }
        )
        corps.send()
        origin.message_post(
            body=self.env._("Réponse envoyée à %s.", self.to_addr),
            subtype_xmlid="mail.mt_note",
        )
        return {"type": "ir.actions.act_window_close"}
