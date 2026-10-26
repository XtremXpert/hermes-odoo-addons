# Part of the imap_client Odoo module. See LICENSE for details.
"""Compte IMAP : la boite du tenant — host, identifiants, synchro."""

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import AccessError
from odoo.exceptions import UserError

from ..services.imap_connection import IMAPConnexion


class ImapAccount(models.Model):
    _name = "imap.account"
    _inherit = ["mail.thread"]
    _description = "Compte IMAP"
    _order = "name"

    name = fields.Char(string="Nom", required=True)
    host = fields.Char(string="Serveur IMAP", required=True)
    port = fields.Integer(string="Port", default=993)
    use_ssl = fields.Boolean(string="SSL", default=True)
    user = fields.Char(string="Utilisateur", required=True)
    password = fields.Char(
        string="Mot de passe",
        groups="imap_client.group_imap_manager",
    )
    folder_ids = fields.One2many("imap.folder", "account_id", string="Dossiers")
    post_to_partner = fields.Boolean(
        string="Ancrer au contact",
        default=True,
        help="Chaque courriel synchronisé est aussi posté au fil du contact correspondant.",
    )
    active = fields.Boolean(default=True)
    last_synced_on = fields.Datetime(string="Dernière synchronisation", readonly=True)

    def _exiger(self):
        if self.env.su or self.env.user.has_group("imap_client.group_imap_manager"):
            return
        raise AccessError(self.env._("Action IMAP réservée aux gestionnaires."))

    def _connexion(self):
        """Un tunnel IMAP vers la boite."""
        self.ensure_one()
        if not self.host or not self.user or not self.password:
            raise UserError(self.env._("Le compte IMAP « %s » n'est pas configuré.", self.name))
        return IMAPConnexion(self.host, self.port, self.user, self.password, self.use_ssl)

    @api.model
    def action_sync(self):
        """Synchroniser les dossiers puis les messages de chaque compte actif."""
        self._exiger()
        for compte in self.search([("active", "=", True)]):
            connexion = compte._connexion()
            try:
                dossiers = connexion.dossiers()
                connexion.quitter()
                compte._sync_dossiers(dossiers)
                for dossier in compte.folder_ids:
                    dossier._sync_messages()
            finally:
                compte.write({"last_synced_on": fields.Datetime.now()})

    def _sync_dossiers(self, noms):
        """Rapatrier la liste des dossiers du serveur."""
        existants = set(self.folder_ids.mapped("name"))
        for nom in noms:
            if nom not in existants:
                self.env["imap.folder"].create({"name": nom, "account_id": self.id})

    def action_tester(self):
        """Tester la connexion IMAP sans rien synchroniser."""
        self._exiger()
        self.ensure_one()
        connexion = self._connexion()
        connexion.quitter()
        self.message_post(body=self.env._("Connexion IMAP réussie."), subtype_xmlid="mail.mt_note")
