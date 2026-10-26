# Part of the imap_client Odoo module. See LICENSE for details.
"""Message IMAP : entete rapatrie, corps a la demande, ancre au contact."""

from odoo import fields
from odoo import models


class ImapMessage(models.Model):
    _name = "imap.message"
    _inherit = ["mail.thread"]
    _description = "Message IMAP"
    _order = "date desc"

    folder_id = fields.Many2one(
        "imap.folder",
        string="Dossier",
        required=True,
        readonly=True,
        ondelete="cascade",
        index=True,
    )
    account_id = fields.Many2one(
        related="folder_id.account_id", string="Compte", store=True, readonly=True
    )
    message_id = fields.Char(string="Message-ID", readonly=True, index=True)
    subject = fields.Char(string="Sujet", readonly=True)
    from_addr = fields.Char(string="De", readonly=True)
    to_addr = fields.Char(string="À", readonly=True)
    date = fields.Datetime(string="Date", readonly=True)
    seen = fields.Boolean(string="Lu", readonly=True, default=False)
    in_reply_to = fields.Char(string="Réponse à", readonly=True)
    body = fields.Html(string="Corps", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Contact", readonly=True, index=True)
    mail_message_id = fields.Many2one("mail.message", string="Message Odoo", readonly=True)

    def _corps(self):
        """Le corps du message, telecharge a la demande."""
        self.ensure_one()
        from email import policy
        from email.parser import BytesParser

        connexion = self.folder_id.account_id._connexion()
        try:
            brut = connexion.corps(self.folder_id.name, self.message_id or "0")
        finally:
            connexion.quitter()
        if not brut:
            return ""
        mail = BytesParser(policy=policy.default).parsebytes(brut)
        for partie in mail.walk():
            if partie.get_content_type() == "text/html":
                return partie.get_content()
            if partie.get_content_type() == "text/plain":
                return "<pre>%s</pre>" % (partie.get_content() or "")
        return ""

    def _post_to_partner(self):
        """Ancrer le courriel au contact Odoo correspondant (de ou a)."""
        compte = self.account_id
        if not compte.post_to_partner:
            return
        email = (self.from_addr or "").lower()
        if "@" in email:
            adresse = email.split("<")[-1].rstrip(">").strip()
            partner = self.env["res.partner"].search([("email", "ilike", adresse)], limit=1)
            if partner:
                msg = partner.message_post(
                    body=self.env._("Courriel entrant : %s — %s", self.from_addr, self.subject),
                    message_type="email",
                    subtype_xmlid="mail.mt_note",
                )
                self.write({"partner_id": partner.id, "mail_message_id": msg.id})

    def action_marquer_lu(self):
        """Marquer le message lu localement et sur le serveur."""
        for message in self:
            if message.seen:
                continue
            connexion = message.folder_id.account_id._connexion()
            try:
                connexion.marquer_lu(message.folder_id.name, message.message_id or "0")
            finally:
                connexion.quitter()
            message.write({"seen": True})

    def action_repondre(self):
        """Ouvrir l'assistant de réponse pré-rempli."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "imap.reply",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_message_id": self.id,
                "default_to_addr": self.from_addr,
                "default_subject": "Re: %s" % (self.subject or "").lstrip("Re: "),
            },
        }

    def action_lire(self):
        """Charger le corps puis le lire."""
        for message in self:
            if not message.body:
                message.write({"body": message._corps()})
            message.action_marquer_lu()
