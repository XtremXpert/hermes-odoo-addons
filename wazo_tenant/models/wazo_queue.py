# Part of the wazo_tenant Odoo module. See LICENSE for details.
"""File d'attente Wazo, miroir local et cycle de vie complet.

Flux de création (mesuré sur confd 1.1) :

1. ``POST /queues`` — la file, portant son libellé ;
2. ``POST /extensions`` — le poste (plage ``queue`` du contexte) ;
3. ``PUT /queues/{id}/extensions/{id}`` — l'association ;
4. ``PUT /queues/{id}/members/users/{uuid}`` — un appel par membre,
   désigné par **uuid** d'utilisateur (comme les groupes d'appel).

La suppression inverse chaque association avant de détruire la file,
en tolérant les 404 — relancer après un échec partiel nettoie proprement.
"""

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError

from ..services.wazo_client import WazoAPIError


class WazoQueue(models.Model):
    _name = "wazo.queue"
    _inherit = ["wazo.extension.mixin"]
    _extension_type = "queue"
    _description = "File d'attente Wazo"
    _rec_name = "name"

    name = fields.Char(string="Nom", required=True)
    extension = fields.Char(string="Poste", required=True)
    member_ids = fields.Many2many(
        "wazo.user",
        string="Membres",
        help="Agents de la file — des usagers Wazo synchronisés.",
    )
    member_count = fields.Integer(
        string="Nombre de membres", compute="_compute_member_count"
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
    remote_queue_id = fields.Integer(string="ID file Wazo", readonly=True, copy=False)
    remote_extension_id = fields.Integer(string="ID poste Wazo", readonly=True, copy=False)
    error_message = fields.Text(string="Dernier message d'erreur", readonly=True, copy=False)
    active = fields.Boolean(default=True)

    @api.depends("member_ids")
    def _compute_member_count(self):
        for queue in self:
            queue.member_count = len(queue.member_ids)

    # ------------------------------------------------------------------
    # Synchronisation
    # ------------------------------------------------------------------

    def _own_extension_owner_ids(self):
        return {"queue": self.remote_queue_id}

    def _adopt_remote_orphan(self, client):
        """Reprise d'une file orpheline : par son nom, puis son poste."""
        response = client.conf("GET", "/queues")
        for queue in response.get("items") or []:
            if queue.get("name") == self.name:
                self.sudo().write({"remote_queue_id": queue["id"]})
                for extension in queue.get("extensions") or []:
                    self.sudo().write({"remote_extension_id": extension["id"]})
                return True
        return False

    def action_sync_wazo(self):
        """Crée (ou reprend) la file et son poste sur Wazo."""
        self.ensure_one()
        if self.wazo_state == "synced":
            raise UserError(
                self.env._("La file %s est déjà synchronisée sur Wazo.", self.name)
            )
        client = self._wazo_client()
        context = self._wazo_line_context()
        # Les membres sont désignés par uuid côté Wazo.
        sans_uuid = self.member_ids.filtered(
            lambda user: not user._ensure_remote_user_uuid(client)
        )
        if sans_uuid:
            raise UserError(
                self.env._(
                    "Ces utilisateurs n'ont pas d'uuid côté Wazo : %s. "
                    "Synchronisez-les d'abord.",
                    ", ".join(sans_uuid.mapped("name")),
                )
            )
        try:
            extension = self._find_wazo_extension(client)
            self._check_extension_allowed(client, context, extension)
            if self.remote_queue_id:
                queue_id = self.remote_queue_id
            else:
                try:
                    queue = client.conf(
                        "POST", "/queues", body={"name": self.name, "label": self.name}
                    )
                except WazoAPIError as error:
                    # Une tentative échouée survit au rollback Odoo : la
                    # file distante est réutilisée par son nom (mesuré :
                    # « Queue already exists » sinon).
                    if "already exists" not in str(error):
                        raise
                    response = client.conf("GET", "/queues")
                    for item in response.get("items") or []:
                        if item.get("name") == self.name:
                            queue = item
                            break
                    else:
                        raise
                queue_id = queue["id"]
                self.sudo().write({"remote_queue_id": queue_id})
            if extension is None:
                extension = client.conf(
                    "POST", "/extensions", body={"exten": self.extension, "context": context}
                )
                self.sudo().write({"remote_extension_id": extension["id"]})
            client.conf(
                "PUT", "/queues/%s/extensions/%s" % (queue_id, extension["id"])
            )
            for user in self.member_ids:
                # Corps exigé (mesuré : sans lui, confd répond 400) —
                # priorité 0 : l'ordre n'a d'effet qu'en stratégie linéaire.
                client.conf(
                    "PUT",
                    "/queues/%s/members/users/%s" % (queue_id, user.remote_user_uuid),
                    body={"priority": 0},
                )
        except UserError:
            raise
        except Exception as error:  # noqa: BLE001 — consigner plutôt que remonter
            self.write({"wazo_state": "error", "error_message": str(error)})
            return False
        self.sudo().write(
            {
                "wazo_state": "synced",
                "remote_queue_id": queue_id,
                "remote_extension_id": extension["id"],
                "error_message": False,
            }
        )
        return True

    def action_delete_wazo(self):
        """Retire la file et son poste de Wazo (idempotent, 404 tolérés)."""
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
            if self.remote_queue_id:
                for user in self.member_ids:
                    if user.remote_user_uuid:
                        _ignore_404(
                            "DELETE",
                            "/queues/%s/members/users/%s"
                            % (self.remote_queue_id, user.remote_user_uuid),
                        )
                if self.remote_extension_id:
                    _ignore_404(
                        "DELETE",
                        "/queues/%s/extensions/%s"
                        % (self.remote_queue_id, self.remote_extension_id),
                    )
                _ignore_404("DELETE", "/queues/%s" % self.remote_queue_id)
            if self.remote_extension_id:
                _ignore_404("DELETE", "/extensions/%s" % self.remote_extension_id)
        except WazoAPIError as error:
            self.write({"wazo_state": "error", "error_message": str(error)})
            return False
        self.sudo().write(
            {
                "wazo_state": "new",
                "remote_queue_id": False,
                "remote_extension_id": False,
                "error_message": False,
            }
        )
        return True

    def action_retry_sync(self):
        self.ensure_one()
        return self.action_sync_wazo()
