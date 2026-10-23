# Part of the wazo_voipms Odoo module. See LICENSE for details.
"""Routage entrant d'un DID VoIP.ms vers une destination Wazo.

Le pont a deux moitiés, chacune idempotente :

* **Wazo** — un ``incall`` dans le contexte ``from-extern`` : le numéro
  composé est associé à une destination (utilisateur ou groupe d'appel) ;
* **VoIP.ms** — ``setDIDRouting`` bascule le DID en routage ``sip:`` vers
  ``sip:<numéro>@<hôte Wazo public>`` : l'appel entrant arrive en SIP sur
  le trunk et déclenche l'incall.

La destination Wazo est un choix entre ``wazo.user`` et
``wazo.ring.group`` — un seul des deux champs est requis, validé par
contrainte : Wazo n'accepte qu'une destination par incall.
"""

from odoo import api
from odoo import fields
from odoo import models
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSAPIError
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSClient
from odoo.addons.wazo_tenant.services.wazo_client import WazoAPIError
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError


class VoIPMSDid(models.Model):
    _inherit = "voipms.did"

    wazo_destination_type = fields.Selection(
        selection=[
            ("none", "Aucune"),
            ("user", "Utilisateur Wazo"),
            ("group", "Groupe d'appel"),
        ],
        string="Destination Wazo",
        default="none",
    )
    wazo_user_id = fields.Many2one("wazo.user", string="Utilisateur Wazo")
    wazo_ring_group_id = fields.Many2one(
        "wazo.ring.group", string="Groupe d'appel"
    )
    wazo_incall_id = fields.Integer(string="ID incall Wazo", readonly=True)
    wazo_incall_extension_id = fields.Integer(
        string="ID extension incall", readonly=True
    )
    wazo_route_state = fields.Selection(
        selection=[
            ("none", "Non routé"),
            ("routed", "Routé vers Wazo"),
            ("error", "Erreur"),
        ],
        string="Routage",
        default="none",
        required=True,
        readonly=True,
    )
    wazo_route_error = fields.Text(string="Erreur de routage", readonly=True)

    # ------------------------------------------------------------------
    # Validation et résolution de la destination
    # ------------------------------------------------------------------

    @api.constrains("wazo_destination_type", "wazo_user_id", "wazo_ring_group_id")
    def _check_wazo_destination(self):
        for did in self:
            if did.wazo_destination_type == "user" and not did.wazo_user_id:
                raise ValidationError(
                    self.env._("Choisissez l'utilisateur Wazo de destination.")
                )
            if did.wazo_destination_type == "group" and not did.wazo_ring_group_id:
                raise ValidationError(
                    self.env._("Choisissez le groupe d'appel de destination.")
                )

    def _wazo_client(self):
        return self.env["wazo.user"]._wazo_client()

    def _wazo_public_host(self):
        """Hôte public du serveur Wazo, pour l'URI SIP du routage VoIP.ms."""
        url = (
            self.env["ir.config_parameter"].sudo().get_str("wazo.url", default="")
        ).strip()
        if not url:
            raise UserError(
                self.env._("Configurez l'URL du serveur Wazo avant le routage.")
            )
        return url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]

    def _destination_payload(self):
        """Corps ``destination`` de l'incall, selon le type choisi."""
        self.ensure_one()
        if self.wazo_destination_type == "user":
            if self.wazo_user_id.wazo_state != "synced":
                raise UserError(
                    self.env._(
                        "L'utilisateur %s n'est pas synchronisé sur Wazo.",
                        self.wazo_user_id.name,
                    )
                )
            return {"type": "user", "user_id": int(self.wazo_user_id.remote_user_id)}
        if self.wazo_destination_type == "group":
            if self.wazo_ring_group_id.wazo_state != "synced":
                raise UserError(
                    self.env._(
                        "Le groupe %s n'est pas synchronisé sur Wazo.",
                        self.wazo_ring_group_id.name,
                    )
                )
            return {
                "type": "group",
                "group_id": self.wazo_ring_group_id.remote_group_id,
            }
        return {"type": "none"}

    def _sip_routing_uri(self):
        """URI SIP que VoIP.ms appellera : ``sip:<DID>@<hôte Wazo>``."""
        return "sip:%s@%s" % (self.number, self._wazo_public_host())

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_route_to_wazo(self):
        """Crée l'incall Wazo puis bascule le routage VoIP.ms en sip:.

        L'ordre est choisi pour ne jamais laisser le DID sans destination :
        le routage VoIP.ms n'est basculé qu'une fois l'incall en place.
        """
        self.ensure_one()
        if self.wazo_route_state == "routed":
            raise UserError(
                self.env._("Le DID %s est déjà routé vers Wazo.", self.number)
            )
        incall_id = self.wazo_incall_id or False
        incall_extension_id = self.wazo_incall_extension_id or False
        try:
            client = self._wazo_client()
            # Incall : créé si absent, destination ré-appliquée sinon.
            if self.wazo_incall_id:
                client.conf(
                    "PUT",
                    "/incalls/%s" % self.wazo_incall_id,
                    body={"destination": self._destination_payload()},
                )
                incall_id = self.wazo_incall_id
                incall_extension_id = self.wazo_incall_extension_id
            else:
                incall = client.conf(
                    "POST",
                    "/incalls",
                    body={
                        "extensions": [
                            {"context": "from-extern", "exten": self.number}
                        ],
                        "destination": self._destination_payload(),
                    },
                )
                incall_id = incall["id"]
                extensions = incall.get("extensions") or []
                incall_extension_id = extensions[0].get("id") if extensions else False
            # Bascule VoIP.ms : sip:<DID>@<hôte Wazo>.
            response = self._voipms_client()._request(
                "setDIDRouting",
                {"did": self.number, "routing": self._sip_routing_uri()},
            )
            if str(response.get("status")) != "success":
                raise UserError(
                    self.env._("VoIP.ms a refusé le routage : %s") % response
                )
        except (WazoAPIError, VoIPMSAPIError, UserError) as error:
            self.sudo().write(
                {
                    "wazo_route_state": "error",
                    "wazo_route_error": str(error),
                    "wazo_incall_id": incall_id,
                }
            )
            return False
        self.sudo().write(
            {
                "wazo_route_state": "routed",
                "wazo_incall_id": incall_id,
                "wazo_incall_extension_id": incall_extension_id or False,
                "wazo_route_error": False,
            }
        )
        return True

    def action_unroute_from_wazo(self):
        """Retire l'incall Wazo et remet le DID en routage hangup.

        Le routage VoIP.ms est d'abord basculé vers ``sys:hangup`` : la
        suppression de l'incall ensuite ne laisse jamais un routage vers
        un Wazo sans destination.
        """
        self.ensure_one()
        client = self._wazo_client()
        try:
            # 1. Retirer le routage VoIP.ms.
            self._voipms_client()._request(
                "setDIDRouting", {"did": self.number, "routing": "sys:hangup"}
            )
            # 2. Supprimer l'incall (dissocier l'extension d'abord si présente).
            if self.wazo_incall_id and self.wazo_incall_extension_id:
                try:
                    client.conf(
                        "DELETE",
                        "/incalls/%s/extensions/%s"
                        % (self.wazo_incall_id, self.wazo_incall_extension_id),
                    )
                except WazoAPIError as error:
                    if "HTTP 404" not in str(error):
                        raise
            if self.wazo_incall_id:
                try:
                    client.conf("DELETE", "/incalls/%s" % self.wazo_incall_id)
                except WazoAPIError as error:
                    if "HTTP 404" not in str(error):
                        raise
            # 3. L'extension « from-extern » devient orpheline : on la retire.
            if self.wazo_incall_extension_id:
                try:
                    client.conf(
                        "DELETE", "/extensions/%s" % self.wazo_incall_extension_id
                    )
                except WazoAPIError as error:
                    if "HTTP 404" not in str(error):
                        raise
        except (WazoAPIError, VoIPMSAPIError) as error:
            self.sudo().write(
                {"wazo_route_state": "error", "wazo_route_error": str(error)}
            )
            return False
        self.sudo().write(
            {
                "wazo_route_state": "none",
                "wazo_incall_id": False,
                "wazo_incall_extension_id": False,
                "wazo_route_error": False,
            }
        )
        return True

    def _voipms_client(self):
        return VoIPMSClient(self.env)
