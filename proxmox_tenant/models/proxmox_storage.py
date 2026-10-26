# Part of the proxmox_tenant Odoo module. See LICENSE for details.
"""Stockage Proxmox : les volumes ou vivent disques, images et sauvegardes."""

from odoo import api
from odoo import fields
from odoo import models

from ..services.proxmox_client import ProxmoxClient
from .fields_bigint import BigInteger


class ProxmoxStorage(models.Model):
    _name = "proxmox.storage"
    _inherit = ["proxmox.sync.mixin"]
    _description = "Stockage Proxmox"
    _order = "node, name"

    name = fields.Char(string="Nom", required=True, readonly=True)
    node = fields.Char(string="Noeud", readonly=True)
    storage_type = fields.Char(string="Type", readonly=True)
    content = fields.Char(string="Contenu", readonly=True)
    active_flag = fields.Char(string="Actif", readonly=True)
    avail = BigInteger(string="Disponible (o)", readonly=True)
    total = BigInteger(string="Total (o)", readonly=True)
    used = BigInteger(string="Utilisé (o)", readonly=True)
    shared = fields.Boolean(string="Partagé", readonly=True)
    active = fields.Boolean(default=True)

    @api.model
    def action_sync_all_from_proxmox(self):
        """Aligner tout l'état local sur le cluster (bouton et menu)."""
        self._exiger("sync")
        return self.sudo()._sync_all_from_proxmox()

    @api.model
    def _sync_all_from_proxmox(self):
        """Rapatrier les stockages (GET /cluster/resources?type=storage)."""
        client = ProxmoxClient(self.env)
        entries = client._request("GET", "/cluster/resources?type=storage") or []
        vus = set()
        for entry in entries:
            nom = entry.get("storage")
            noeud = entry.get("node") or ""
            if not nom:
                continue
            vus.add((nom, noeud))
            valeurs = {
                "node": noeud,
                "storage_type": entry.get("plugintype") or entry.get("type") or "",
                "content": str(entry.get("content") or ""),
                "avail": int(entry.get("avail") or 0),
                "total": int(entry.get("maxdisk") or 0),
                "used": int(entry.get("disk") or 0),
                "shared": bool(entry.get("shared")),
                "active": True,
                "last_synced_on": fields.Datetime.now(),
            }
            stockage = self.search([("name", "=", nom), ("node", "=", noeud)], limit=1)
            if stockage:
                stockage.write(valeurs)
            else:
                self.create(dict(valeurs, name=nom))
        for stockage in self.search([("active", "=", True)]):
            if (stockage.name, stockage.node or "") not in vus:
                stockage.write({"active": False})
