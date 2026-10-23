# Part of the wazo_tenant Odoo module. See LICENSE for details.
"""Parc de stationnement Wazo — cycle de vie complet.

Composer le poste du parc met l'appel en attente sur un **créneau**
entre ``slots_start`` et ``slots_end`` (mesuré : chaînes côté confd) ;
recomposer un créneau reprend l'appel. Le poste du parc n'a pas de
plage déclarée côté Wazo — seul le contrôle croisé des autres types
s'applique.
"""

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

from ..services.wazo_client import WazoAPIError


class WazoParking(models.Model):
    _name = "wazo.parking"
    _inherit = ["wazo.extension.mixin"]
    _extension_type = "parking"
    _description = "Parc de stationnement Wazo"
    _rec_name = "name"

    name = fields.Char(string="Nom", required=True)
    extension = fields.Char(
        string="Poste du parc",
        required=True,
        help="Composer ce poste parque l'appel courant.",
    )
    slots_start = fields.Char(string="Premier créneau", required=True)
    slots_end = fields.Char(string="Dernier créneau", required=True)
    park_timeout = fields.Integer(
        string="Délai avant retour (s)", default=45, help="Au-delà, l'appel revient."
    )
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
    remote_parking_lot_id = fields.Integer(
        string="ID parc Wazo", readonly=True, copy=False
    )
    remote_extension_id = fields.Integer(string="ID poste Wazo", readonly=True, copy=False)
    error_message = fields.Text(string="Dernier message d'erreur", readonly=True, copy=False)
    active = fields.Boolean(default=True)

    @api.constrains("slots_start", "slots_end")
    def _check_slots(self):
        for parc in self:
            for slot in (parc.slots_start, parc.slots_end):
                if slot and not slot.isdigit():
                    raise ValidationError(
                        self.env._("Les créneaux sont des numéros (ex. 701, 710).")
                    )
            if (
                parc.slots_start
                and parc.slots_end
                and int(parc.slots_end) < int(parc.slots_start)
            ):
                raise ValidationError(
                    self.env._("Le dernier créneau suit le premier.")
                )

    def _own_extension_owner_ids(self):
        return {"parking_lot": self.remote_parking_lot_id}

    def _master_client(self):
        """Client au niveau MAÎTRE : le plugin des parcs ignore l'en-tête
        ``Wazo-Tenant`` — création, lecture, association, tout (mesuré :
        un parc créé « dans » le tenant atterrit chez le maître, et
        l'association croisée répond 400). Le parc est une ressource
        d'infrastructure du PBX, comme le veut Wazo.
        """
        from ..services.wazo_client import WazoClient

        return WazoClient(self.env)

    def _resolve_parking_context(self, client):
        """Nom du contexte des parcs, créé au besoin — au maître.

        Le maître d'un Wazo neuf n'a souvent AUCUN contexte (mesuré) :
        sans contexte, le poste du parc ne peut pas exister.
        """
        response = client.conf("GET", "/contexts")
        items = response.get("items") or [] if isinstance(response, dict) else []
        for item in items:
            if item.get("label") == "parking":
                if item.get("type") != "internal":
                    client.conf(
                        "PUT",
                        "/contexts/%s" % item["id"],
                        body={"type": "internal"},
                    )
                return item["name"]
        # Type « internal » — mesuré dans le validateur confd : le poste
        # d'un parc doit vivre dans un contexte interne.
        created = client.conf(
            "POST", "/contexts", body={"label": "parking", "type": "internal"}
        )
        return created["name"]

    def action_sync_wazo(self):
        """Crée (ou reprend) le parc et son poste sur Wazo."""
        self.ensure_one()
        if self.wazo_state == "synced":
            raise UserError(
                self.env._("Le parc %s est déjà synchronisé sur Wazo.", self.name)
            )
        client = self._master_client()
        context = self._resolve_parking_context(client)
        try:
            # Recherche du poste au maître, sans contrôle de plage : le
            # contexte « parking » du maître n'en déclare pas.
            existing = None
            response = client.conf(
                "GET", "/extensions", params={"exten": self.extension, "context": context}
            )
            items = response.get("items") or [] if isinstance(response, dict) else []
            for item in items:
                if str(item.get("exten")) == str(self.extension):
                    existing = item
                    break
            if self.remote_parking_lot_id:
                parking_id = self.remote_parking_lot_id
            else:
                parking = client.conf(
                    "POST",
                    "/parkinglots",
                    body={
                        "name": self.name,
                        "slots_start": self.slots_start,
                        "slots_end": self.slots_end,
                        "timeout": self.park_timeout,
                    },
                )
                parking_id = parking["id"]
                self.sudo().write({"remote_parking_lot_id": parking_id})
            if existing is None:
                existing = client.conf(
                    "POST", "/extensions", body={"exten": self.extension, "context": context}
                )
                self.sudo().write({"remote_extension_id": existing["id"]})
            client.conf(
                "PUT",
                "/parkinglots/%s/extensions/%s" % (parking_id, existing["id"]),
            )
        except UserError:
            raise
        except Exception as error:  # noqa: BLE001 — consigner plutôt que remonter
            self.write({"wazo_state": "error", "error_message": str(error)})
            return False
        self.sudo().write(
            {
                "wazo_state": "synced",
                "remote_parking_lot_id": parking_id,
                "remote_extension_id": existing["id"],
                "error_message": False,
            }
        )
        return True

    def action_delete_wazo(self):
        """Retire le parc et son poste de Wazo (idempotent)."""
        self.ensure_one()
        client = self._master_client()

        def _ignore_404(method, path):
            try:
                client.conf(method, path)
            except WazoAPIError as error:
                if "HTTP 404" not in str(error):
                    raise
            return True

        try:
            if self.remote_parking_lot_id and self.remote_extension_id:
                _ignore_404(
                    "DELETE",
                    "/parkinglots/%s/extensions/%s"
                    % (self.remote_parking_lot_id, self.remote_extension_id),
                )
            if self.remote_parking_lot_id:
                _ignore_404("DELETE", "/parkinglots/%s" % self.remote_parking_lot_id)
            if self.remote_extension_id:
                _ignore_404("DELETE", "/extensions/%s" % self.remote_extension_id)
        except WazoAPIError as error:
            self.write({"wazo_state": "error", "error_message": str(error)})
            return False
        self.sudo().write(
            {
                "wazo_state": "new",
                "remote_parking_lot_id": False,
                "remote_extension_id": False,
                "error_message": False,
            }
        )
        return True

    def action_retry_sync(self):
        self.ensure_one()
        return self.action_sync_wazo()
