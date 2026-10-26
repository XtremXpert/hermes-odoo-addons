# Part of the imap_client Odoo module. See LICENSE for details.
"""Dossier IMAP : INBOX, Envoyes, Brouillons — conteneur des messages."""

from odoo import api
from odoo import fields
from odoo import models

LIMITE_SYNC = 50


class ImapFolder(models.Model):
    _name = "imap.folder"
    _inherit = ["mail.thread"]
    _description = "Dossier IMAP"
    _order = "account_id, name"

    name = fields.Char(string="Dossier", required=True, readonly=True)
    account_id = fields.Many2one(
        "imap.account", string="Compte", required=True, readonly=True, ondelete="cascade"
    )
    message_ids = fields.One2many("imap.message", "folder_id", string="Messages")
    unread = fields.Integer(string="Non lus", compute="_compute_unread")

    _imap_folder_uniq = models.Constraint("unique(account_id, name)", "Ce dossier existe déjà.")

    def _compute_unread(self):
        """Nombre de messages non lus du dossier."""
        for dossier in self:
            dossier.unread = self.env["imap.message"].search_count(
                [("folder_id", "=", dossier.id), ("seen", "=", False)]
            )

    @api.model
    def _sync_messages(self):
        """Rapatrier les entêtes des LIMITE_SYNC derniers messages du dossier."""
        from email import policy
        from email.parser import BytesParser

        connexion = self.account_id._connexion()
        try:
            entetes = connexion.entetes(self.name, limite=LIMITE_SYNC)
        finally:
            connexion.quitter()
        Msg = self.env["imap.message"].sudo()
        for entete in entetes:
            brut = entete.get("raw") or b""
            mail = BytesParser(policy=policy.default).parsebytes(brut)
            # Le UID IMAP arrive dans les flags du fetch — le Message-ID suffit ici.
            deja = Msg.search(
                [("folder_id", "=", self.id), ("message_id", "=", mail.get("Message-ID", ""))],
                limit=1,
            )
            if deja:
                continue
            message = Msg.create(
                {
                    "folder_id": self.id,
                    "message_id": mail.get("Message-ID", ""),
                    "subject": mail.get("Subject", "(sans sujet)"),
                    "from_addr": mail.get("From", ""),
                    "to_addr": mail.get("To", ""),
                    "date": fields.Datetime.now(),
                    "seen": "Seen" in str(entete.get("flags") or ""),
                    "in_reply_to": mail.get("In-Reply-To", ""),
                }
            )
            message._post_to_partner()
