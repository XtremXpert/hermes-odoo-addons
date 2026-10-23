# Part of the wazo_tenant Odoo module. See LICENSE for details.
"""Messagerie vocale Wazo autonome — cycle de vie complet.

Les usagers Wazo portent déjà leur messagerie (créée à leur
synchronisation). Celle-ci est **autonome** : une boîte pour un renvoi
entrant, un parc, une file — tout numéro qui doit pouvoir recueillir
des messages sans être un usager. Le numéro est celui de la boîte, pas
un poste : il vit dans le contexte du tenant (mesuré : confd refuse un
contexte inconnu).
"""

from odoo import fields
from odoo import models
from odoo.exceptions import UserError

from ..services.wazo_client import WazoAPIError


class WazoVoicemail(models.Model):
    _name = "wazo.voicemail"
    # Le mixin donne le client Wazo et le contexte du tenant ; la
    # messagerie n'a pas de poste à valider.
    _inherit = ["wazo.extension.mixin"]
    _extension_type = "voicemail"
    _description = "Messagerie vocale Wazo (autonome)"
    _rec_name = "name"

    name = fields.Char(string="Nom", required=True)
    number = fields.Char(
        string="Numéro de boîte",
        required=True,
        help="Numéro composé pour consulter la boîte (ex. le poste du "
        "service, ou le numéro du DID sans indicatif).",
    )
    language = fields.Char(string="Langue", default="fr_CA")
    wazo_state = fields.Selection(
        selection=[
            ("new", "Nouveau"),
            ("synced", "Synchronisé"),
            ("error", "Erreur"),
        ],
        string="État",
        default="new",
        required=True,
    )
    remote_voicemail_id = fields.Integer(
        string="ID messagerie Wazo", readonly=True, copy=False
    )
    error_message = fields.Text(string="Dernier message d'erreur", readonly=True, copy=False)
    active = fields.Boolean(default=True)


    def action_sync_wazo(self):
        """Crée la boîte sur Wazo, dans le contexte du tenant."""
        self.ensure_one()
        if self.wazo_state == "synced":
            raise UserError(
                self.env._("La messagerie %s est déjà synchronisée sur Wazo.", self.name)
            )
        client = self._wazo_client()
        try:
            if self.remote_voicemail_id:
                voicemail_id = self.remote_voicemail_id
            else:
                try:
                    voicemail = client.conf(
                        "POST",
                        "/voicemails",
                        body={
                            "name": self.name,
                            "number": self.number,
                            "context": self._wazo_line_context(),
                            "language": self.language or "fr_CA",
                        },
                    )
                except WazoAPIError as error:
                    # Réutilisation : la boîte d'une tentative échouée
                    # survit au rollback Odoo (mesuré : « Voicemail
                    # already exists » sinon) — reprise par numéro.
                    if "already exists" not in str(error):
                        raise
                    response = client.conf("GET", "/voicemails")
                    for box in response.get("items") or []:
                        if box.get("number") == self.number:
                            voicemail = box
                            break
                    else:
                        raise
                voicemail_id = voicemail["id"]
        except WazoAPIError as error:
            self.write({"wazo_state": "error", "error_message": str(error)})
            return False
        self.sudo().write(
            {
                "wazo_state": "synced",
                "remote_voicemail_id": voicemail_id,
                "error_message": False,
            }
        )
        return True

    def action_delete_wazo(self):
        """Retire la boîte de Wazo — refusée par confd si elle est encore
        associée à un usager (mesuré : HTTP 400)."""
        self.ensure_one()
        client = self._wazo_client()
        try:
            if self.remote_voicemail_id:
                client.conf("DELETE", "/voicemails/%s" % self.remote_voicemail_id)
        except WazoAPIError as error:
            message = str(error)
            if "HTTP 404" in message:
                pass
            else:
                # Associée à un usager : le message dit quoi détacher.
                self.write({"wazo_state": "error", "error_message": message})
                return False
        self.sudo().write(
            {
                "wazo_state": "new",
                "remote_voicemail_id": False,
                "error_message": False,
            }
        )
        return True

    def action_retry_sync(self):
        self.ensure_one()
        return self.action_sync_wazo()
