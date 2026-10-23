# Part of the wazo_tenant Odoo module. See LICENSE for details.
"""Menu vocal (IVR) Wazo — cycle de vie complet.

L'IVR n'a **pas de poste propre** : il se rejoint par un renvoi entrant
(mesuré : le schéma confd ne connaît l'IVR que par ses incalls). Le menu
— ses choix, touche par touche — se bâtit dans l'interface Wazo ; ce
module crée la coquille et la rend **destination** d'un DID routé
(``wazo_voipms`` : routage entrant → menu vocal).
"""

from odoo import fields
from odoo import models
from odoo.exceptions import UserError

from ..services.wazo_client import WazoAPIError


class WazoIVR(models.Model):
    _name = "wazo.ivr"
    # Le mixin donne le client Wazo et le contexte du tenant ; l'IVR
    # n'a pas de poste, donc aucune validation de poste ne s'applique.
    _inherit = ["wazo.extension.mixin"]
    _extension_type = "ivr"
    _description = "Menu vocal (IVR) Wazo"
    _rec_name = "name"

    name = fields.Char(string="Nom", required=True)
    #: Son du menu, exigé par confd (mesuré) : « system » par défaut —
    #: l'administrateur peut pointer un son personnalisé.
    menu_sound = fields.Char(string="Son du menu", default="system", required=True)
    timeout = fields.Integer(string="Délai (secondes)", default=5)
    max_tries = fields.Integer(string="Essais maximum", default=2)
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
    remote_ivr_id = fields.Integer(string="ID menu Wazo", readonly=True, copy=False)
    error_message = fields.Text(string="Dernier message d'erreur", readonly=True, copy=False)
    active = fields.Boolean(default=True)

    def action_sync_wazo(self):
        """Crée le menu sur Wazo — coquille : les choix se bâtissent côté Wazo."""
        self.ensure_one()
        if self.wazo_state == "synced":
            raise UserError(
                self.env._("Le menu %s est déjà synchronisé sur Wazo.", self.name)
            )
        client = self._wazo_client()
        try:
            if self.remote_ivr_id:
                ivr_id = self.remote_ivr_id
            else:
                ivr = client.conf(
                    "POST",
                    "/ivr",
                    body={
                        "name": self.name,
                        "menu_sound": self.menu_sound,
                        "timeout": self.timeout,
                        "max_tries": self.max_tries,
                        "choices": [],
                    },
                )
                ivr_id = ivr["id"]
        except WazoAPIError as error:
            self.write({"wazo_state": "error", "error_message": str(error)})
            return False
        self.sudo().write(
            {
                "wazo_state": "synced",
                "remote_ivr_id": ivr_id,
                "error_message": False,
            }
        )
        return True

    def action_delete_wazo(self):
        """Retire le menu de Wazo (idempotent)."""
        self.ensure_one()
        client = self._wazo_client()
        try:
            if self.remote_ivr_id:
                try:
                    client.conf("DELETE", "/ivr/%s" % self.remote_ivr_id)
                except WazoAPIError as error:
                    if "HTTP 404" not in str(error):
                        raise
        except WazoAPIError as error:
            self.write({"wazo_state": "error", "error_message": str(error)})
            return False
        self.sudo().write(
            {
                "wazo_state": "new",
                "remote_ivr_id": False,
                "error_message": False,
            }
        )
        return True

    def action_retry_sync(self):
        self.ensure_one()
        return self.action_sync_wazo()
