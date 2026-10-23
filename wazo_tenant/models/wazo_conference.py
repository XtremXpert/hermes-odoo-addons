# Part of the wazo_tenant Odoo module. See LICENSE for details.
"""Salle de conférence Wazo — cycle de vie complet.

Flux de création (mesuré) : ``POST /conferences`` avec nom, code PIN
optionnel et plafond d'usagers, puis le poste (plage ``conference``) et
``PUT /conferences/{id}/extensions/{id}``.
"""

from odoo import fields
from odoo import models
from odoo.exceptions import UserError

from ..services.wazo_client import WazoAPIError


class WazoConference(models.Model):
    _name = "wazo.conference"
    _inherit = ["wazo.extension.mixin"]
    _extension_type = "conference"
    _description = "Salle de conférence Wazo"
    _rec_name = "name"

    name = fields.Char(string="Nom", required=True)
    extension = fields.Char(string="Poste", required=True)
    pin = fields.Char(
        string="Code PIN",
        help="Code à composer pour rejoindre la salle (vide = ouvert à tous).",
    )
    admin_pin = fields.Char(
        string="Code PIN animateur",
        help="Code de l'animateur — ouvre la salle verrouillée.",
    )
    max_users = fields.Integer(string="Usagers maximum", default=50)
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
    remote_conference_id = fields.Integer(
        string="ID conférence Wazo", readonly=True, copy=False
    )
    remote_extension_id = fields.Integer(string="ID poste Wazo", readonly=True, copy=False)
    error_message = fields.Text(string="Dernier message d'erreur", readonly=True, copy=False)
    active = fields.Boolean(default=True)

    def _conference_body(self):
        """Corps du ``POST /conferences`` — seuls les champs remplis."""
        body = {"name": self.name, "max_users": self.max_users}
        if self.pin:
            body["pin"] = self.pin
        if self.admin_pin:
            body["admin_pin"] = self.admin_pin
        return body

    def _own_extension_owner_ids(self):
        return {"conference": self.remote_conference_id}

    def _adopt_remote_orphan(self, client):
        """Reprise d'une salle orpheline : par son nom, puis son poste."""
        response = client.conf("GET", "/conferences")
        for room in response.get("items") or []:
            if room.get("name") == self.name:
                self.sudo().write({"remote_conference_id": room["id"]})
                for extension in room.get("extensions") or []:
                    self.sudo().write({"remote_extension_id": extension["id"]})
                return True
        return False

    def action_sync_wazo(self):
        """Crée (ou reprend) la salle et son poste sur Wazo."""
        self.ensure_one()
        if self.wazo_state == "synced":
            raise UserError(
                self.env._("La conférence %s est déjà synchronisée sur Wazo.", self.name)
            )
        client = self._wazo_client()
        context = self._wazo_line_context()
        try:
            extension = self._find_wazo_extension(client)
            self._check_extension_allowed(client, context, extension)
            if self.remote_conference_id:
                conference_id = self.remote_conference_id
            else:
                conference = client.conf("POST", "/conferences", body=self._conference_body())
                conference_id = conference["id"]
                self.sudo().write({"remote_conference_id": conference_id})
            if extension is None:
                extension = client.conf(
                    "POST", "/extensions", body={"exten": self.extension, "context": context}
                )
                self.sudo().write({"remote_extension_id": extension["id"]})
            client.conf(
                "PUT", "/conferences/%s/extensions/%s" % (conference_id, extension["id"])
            )
        except UserError:
            raise
        except Exception as error:  # noqa: BLE001 — consigner plutôt que remonter
            self.write({"wazo_state": "error", "error_message": str(error)})
            return False
        self.sudo().write(
            {
                "wazo_state": "synced",
                "remote_conference_id": conference_id,
                "remote_extension_id": extension["id"],
                "error_message": False,
            }
        )
        return True

    def action_delete_wazo(self):
        """Retire la salle et son poste de Wazo (idempotent)."""
        self.ensure_one()
        client = self._wazo_client()

        def _ignore_404(method, path):
            try:
                client.conf(method, path)
            except WazoAPIError as error:
                if "HTTP 404" not in str(error):
                    raise
            return True

        try:
            if self.remote_conference_id and self.remote_extension_id:
                _ignore_404(
                    "DELETE",
                    "/conferences/%s/extensions/%s"
                    % (self.remote_conference_id, self.remote_extension_id),
                )
            if self.remote_conference_id:
                _ignore_404("DELETE", "/conferences/%s" % self.remote_conference_id)
            if self.remote_extension_id:
                _ignore_404("DELETE", "/extensions/%s" % self.remote_extension_id)
        except WazoAPIError as error:
            self.write({"wazo_state": "error", "error_message": str(error)})
            return False
        self.sudo().write(
            {
                "wazo_state": "new",
                "remote_conference_id": False,
                "remote_extension_id": False,
                "error_message": False,
            }
        )
        return True

    def action_retry_sync(self):
        self.ensure_one()
        return self.action_sync_wazo()
