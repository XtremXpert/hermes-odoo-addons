# Part of the proxmox_tenant Odoo module. See LICENSE for details.
"""Pool Proxmox : le groupement logique qui porte le perimetre du tenant."""

from odoo import api
from odoo import fields
from odoo import models

from ..services.proxmox_client import ProxmoxClient


class ProxmoxPool(models.Model):
    _name = "proxmox.pool"
    _inherit = ["proxmox.sync.mixin"]
    _description = "Pool Proxmox"
    _order = "name"

    name = fields.Char(string="Pool", required=True, readonly=True)
    description = fields.Char(string="Description", readonly=True)
    members = fields.Integer(string="Membres", readonly=True)
    active = fields.Boolean(default=True)

    _proxmox_pool_name_uniq = models.Constraint("unique(name)", "Ce pool est déjà déclaré.")

    @api.model
    def action_sync_all_from_proxmox(self):
        """Aligner tout l'état local sur le cluster (bouton et menu)."""
        self._exiger("sync")
        return self.sudo()._sync_all_from_proxmox()

    @api.model
    def _sync_all_from_proxmox(self):
        """Rapatrier les pools (GET /pools), dans le perimetre du tenant."""
        client = ProxmoxClient(self.env)
        entries = client._request("GET", "/pools") or []
        autorises = self._pools_autorises()
        vus = set()
        for entry in entries:
            nom = entry.get("poolid") or entry.get("pool") or ""
            if not nom:
                continue
            if autorises is not None and nom not in autorises:
                continue
            vus.add(nom)
            membres = len(entry.get("members") or [])
            valeurs = {
                "description": entry.get("comment") or "",
                "members": membres,
                "active": True,
                "last_synced_on": fields.Datetime.now(),
            }
            pool = self.search([("name", "=", nom)], limit=1)
            if pool:
                pool.write(valeurs)
            else:
                self.create(dict(valeurs, name=nom))
        self.search([("name", "not in", list(vus)), ("active", "=", True)]).write({"active": False})
