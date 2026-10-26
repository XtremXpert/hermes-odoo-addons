# Part of the proxmox_tenant Odoo module. See LICENSE for details.
"""Noeud : la machine hote d'un serveur Proxmox qui porte VMs et conteneurs."""

from odoo import api
from odoo import fields
from odoo import models

from .fields_bigint import BigInteger


class ProxmoxNode(models.Model):
    _name = "proxmox.node"
    _inherit = ["proxmox.sync.mixin"]
    _description = "Noeud Proxmox"
    _order = "server_id, name"

    server_id = fields.Many2one(
        "proxmox.server", string="Serveur", required=True, readonly=True,
        ondelete="cascade", index=True,
    )
    name = fields.Char(string="Nom", required=True, readonly=True)
    status = fields.Char(string="État", readonly=True)
    uptime = fields.Integer(string="Disponibilité (s)", readonly=True)
    cpu = fields.Float(string="CPU", readonly=True)
    mem_used = BigInteger(string="Mémoire utilisée (o)", readonly=True)
    mem_max = BigInteger(string="Mémoire totale (o)", readonly=True)
    disk_used = BigInteger(string="Disque utilisé (o)", readonly=True)
    disk_max = BigInteger(string="Disque total (o)", readonly=True)
    active = fields.Boolean(default=True)

    _proxmox_node_uniq = models.Constraint(
        "unique(server_id, name)", "Ce noeud est déjà déclaré sur ce serveur."
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
            try:
                entries = serveur._client()._request("GET", "/cluster/resources?type=node") or []
            except ProxmoxAPIError:
                continue
            vus = set()
            for entry in entries:
                nom = entry.get("node")
                if not nom:
                    continue
                vus.add(nom)
                valeurs = {
                    "server_id": serveur.id,
                    "status": entry.get("status") or "",
                    "uptime": int(entry.get("uptime") or 0),
                    "cpu": float(entry.get("cpu") or 0.0),
                    "mem_used": int(entry.get("mem") or 0),
                    "mem_max": int(entry.get("maxmem") or 0),
                    "disk_used": int(entry.get("disk") or 0),
                    "disk_max": int(entry.get("maxdisk") or 0),
                    "active": True,
                    "last_synced_on": fields.Datetime.now(),
                }
                noeud = self.search(
                    [("server_id", "=", serveur.id), ("name", "=", nom)], limit=1
                )
                if noeud:
                    noeud.write(valeurs)
                else:
                    self.create(dict(valeurs, name=nom))
            self.search(
                [("server_id", "=", serveur.id), ("name", "not in", list(vus)),
                 ("active", "=", True)]
            ).write({"active": False})
