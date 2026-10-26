# Part of the proxmox_tenant Odoo module. See LICENSE for details.
"""Pool Proxmox : le groupement logique, par serveur."""

from odoo import api
from odoo import fields
from odoo import models


class ProxmoxPool(models.Model):
    _name = "proxmox.pool"
    _inherit = ["proxmox.sync.mixin"]
    _description = "Pool Proxmox"
    _order = "server_id, name"

    server_id = fields.Many2one(
        "proxmox.server", string="Serveur", required=True, readonly=True,
        ondelete="cascade", index=True,
    )
    name = fields.Char(string="Pool", required=True, readonly=True)
    description = fields.Char(string="Description", readonly=True)
    members = fields.Integer(string="Membres", readonly=True)
    active = fields.Boolean(default=True)

    _proxmox_pool_uniq = models.Constraint(
        "unique(server_id, name)", "Ce pool est déjà déclaré sur ce serveur."
    )

    @api.model
    def action_sync_all_from_proxmox(self):
        self._exiger("sync")
        return self.sudo()._sync_all_from_proxmox()

    @api.model
    def _sync_all_from_proxmox(self):
        from ..services.proxmox_client import ProxmoxAPIError
        Server = self.env["proxmox.server"].sudo()
        for serveur in Server._serveurs_actifs():
            pools = (
                {p.strip() for p in (serveur.allowed_pools or "").split(",") if p.strip()}
                or None
            )
            try:
                entries = serveur._client()._request("GET", "/pools") or []
            except ProxmoxAPIError:
                continue
            vus = set()
            for entry in entries:
                nom = entry.get("poolid") or entry.get("pool") or ""
                if not nom:
                    continue
                if pools is not None and nom not in pools:
                    continue
                vus.add(nom)
                valeurs = {
                    "server_id": serveur.id,
                    "description": entry.get("comment") or "",
                    "members": len(entry.get("members") or []),
                    "active": True,
                    "last_synced_on": fields.Datetime.now(),
                }
                pool = self.search(
                    [("server_id", "=", serveur.id), ("name", "=", nom)], limit=1
                )
                if pool:
                    pool.write(valeurs)
                else:
                    self.create(dict(valeurs, name=nom))
            self.search(
                [("server_id", "=", serveur.id), ("name", "not in", list(vus)),
                 ("active", "=", True)]
            ).write({"active": False})
