# Part of the mailcow_admin Odoo module. See LICENSE for details.
"""Assistant de création d'un mot de passe applicatif Mailcow.

Le mot de passe est fabriqué ici : la spécification le décrit en **entrée** de
la requête, et la réponse du serveur ne le rend jamais. On le montre une fois à
l'administrateur pour qu'il le copie, on ne le range nulle part, et le fil de
la boîte ne retient que le geste.
"""

import secrets

from odoo import fields
from odoo import models

from ..services.mailcow_client import MailcowClient

PROTOCOLES = [
    ("imap_access", "IMAP"),
    ("dav_access", "Calendrier et contacts (DAV)"),
    ("smtp_access", "SMTP"),
    ("eas_access", "ActiveSync"),
    ("pop3_access", "POP3"),
    ("sieve_access", "Filtres (Sieve)"),
]


def _message(type_, titre, texte):
    return {
        "type": "ir.actions.client",
        "tag": "display_notification",
        "params": {"type": type_, "title": titre, "message": texte, "sticky": type_ != "success"},
    }


class MailcowAppPasswordWizard(models.TransientModel):
    _name = "mailcow.app.password.wizard"
    _description = "Nouveau mot de passe applicatif Mailcow"

    mailbox_id = fields.Many2one(
        "mailcow.mailbox", string="Boîte", required=True, ondelete="cascade"
    )
    app_name = fields.Char(
        string="Nom de l'application",
        required=True,
        help="Le nom que portera ce mot de passe sur le serveur "
        "(ex. wordpress, telephone, scanner).",
    )
    protocols = fields.Selection(
        [("all", "Tous les protocoles (recommandé)"), *PROTOCOLES],
        string="Protocoles",
        default="all",
        required=True,
    )

    def action_create_app_password(self):
        """Créer le mot de passe sur le serveur et le montrer une fois."""
        self.ensure_one()
        if not self.app_name or not self.app_name.strip():
            return _message(
                "warning",
                "Mailcow",
                "Donnez un nom à ce mot de passe : c'est ainsi que "
                "vous le reconnaîtrez sur le serveur.",
            )
        protocoles = [nom for nom, _ in PROTOCOLES] if self.protocols == "all" else [self.protocols]
        # C'est à nous de fabriquer le mot de passe : la spécification le décrit
        # en entrée de la requête, et la réponse du serveur ne le rend jamais.
        mot_de_passe = secrets.token_urlsafe(24)
        client = MailcowClient(self.env)
        client._request(
            "POST",
            "/add/app-passwd",
            {
                "active": "1",
                "username": self.mailbox_id.email,
                "app_name": self.app_name.strip(),
                "app_passwd": mot_de_passe,
                "app_passwd2": mot_de_passe,
                "protocols": protocoles,
            },
        )
        self.mailbox_id._journaliser(
            "Mot de passe applicatif « %s » créé sur Mailcow." % self.app_name.strip()
        )
        return _message(
            "success",
            "Mailcow",
            "Mot de passe applicatif « %s » pour %s :\n\n%s\n\n"
            "Copiez-le maintenant : Odoo ne le garde pas."
            % (self.app_name.strip(), self.mailbox_id.email, mot_de_passe),
        )
