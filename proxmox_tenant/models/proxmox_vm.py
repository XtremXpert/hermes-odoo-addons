# Part of the proxmox_tenant Odoo module. See LICENSE for details.
"""Machine Proxmox : VM (qemu) ou conteneur (lxc), par serveur du tenant."""

from odoo import api
from odoo import fields
from odoo import models

from .fields_bigint import BigInteger

STATUTS = [
    ("running", "en fonction"),
    ("stopped", "arrêtée"),
    ("paused", "en pause"),
]


class ProxmoxVm(models.Model):
    _name = "proxmox.vm"
    _inherit = ["proxmox.sync.mixin"]
    _description = "Machine Proxmox"
    _order = "server_id, vmid"

    server_id = fields.Many2one(
        "proxmox.server", string="Serveur", required=True, readonly=True,
        ondelete="cascade", index=True,
    )
    vmid = fields.Integer(string="VMID", required=True, readonly=True)
    name = fields.Char(string="Nom", readonly=True)
    node = fields.Char(string="Noeud", readonly=True)
    machine_type = fields.Selection(
        [("qemu", "VM"), ("lxc", "Conteneur")], string="Type", readonly=True
    )
    status = fields.Selection(STATUTS, string="État", readonly=True)
    pool_name = fields.Char(string="Pool", readonly=True)
    cpus = fields.Float(string="vCPU", readonly=True)
    mem_max = BigInteger(string="Mémoire (o)", readonly=True)
    disk_max = BigInteger(string="Disque (o)", readonly=True)
    mem_used = BigInteger(string="Mémoire utilisée (o)", readonly=True)
    disk_used = BigInteger(string="Disque utilisé (o)", readonly=True)
    uptime = fields.Integer(string="Disponibilité (s)", readonly=True)
    active = fields.Boolean(default=True)

    _proxmox_vm_uniq = models.Constraint(
        "unique(server_id, vmid)", "Ce VMID est déjà déclaré sur ce serveur."
    )

    @api.model
    def action_sync_all_from_proxmox(self):
        """Aligner tout l'état local sur les serveurs (bouton et menu)."""
        self._exiger("sync")
        return self.sudo()._sync_all_from_proxmox()

    @api.model
    def _sync_all_from_proxmox(self):
        """Rapatrier les machines de chaque serveur actif du tenant."""
        from ..services.proxmox_client import ProxmoxAPIError
        Server = self.env["proxmox.server"].sudo()
        for serveur in Server._serveurs_actifs():
            pools = (
                {p.strip() for p in (serveur.allowed_pools or "").split(",") if p.strip()}
                or None
            )
            try:
                entries = serveur._client()._request("GET", "/cluster/resources?type=vm") or []
            except ProxmoxAPIError:
                continue
            vus = set()
            for entry in entries:
                vmid = entry.get("vmid")
                pool = entry.get("pool") or ""
                if not vmid:
                    continue
                if pools is not None and pool not in pools:
                    continue
                vus.add(vmid)
                valeurs = {
                    "server_id": serveur.id,
                    "name": entry.get("name") or "",
                    "node": entry.get("node") or "",
                    "machine_type": "lxc" if entry.get("type") == "lxc" else "qemu",
                    "status": entry.get("status") or "stopped",
                    "pool_name": pool,
                    "cpus": float(entry.get("maxcpu") or 0),
                    "mem_max": int(entry.get("maxmem") or 0),
                    "disk_max": int(entry.get("maxdisk") or 0),
                    "mem_used": int(entry.get("mem") or 0),
                    "disk_used": int(entry.get("disk") or 0),
                    "uptime": int(entry.get("uptime") or 0),
                    "active": True,
                    "last_synced_on": fields.Datetime.now(),
                }
                machine = self.search(
                    [("server_id", "=", serveur.id), ("vmid", "=", vmid)], limit=1
                )
                if machine:
                    machine.write(valeurs)
                else:
                    self.create(dict(valeurs, vmid=vmid))
            self.search(
                [("server_id", "=", serveur.id), ("vmid", "not in", list(vus)),
                 ("active", "=", True)]
            ).write({"active": False})

    def _chemin_statut(self):
        """Le chemin API de l'etat de la machine sur son serveur/noeud."""
        self.ensure_one()
        return "/nodes/%s/%s/%s/status" % (self.node, self.machine_type, self.vmid)

    def _agir_sur_statut(self, action, libelle):
        """Poster start/stop/shutdown/reboot sur le serveur de la machine."""
        self._exiger("user")
        self.ensure_one()
        self.server_id._client()._request(
            "POST", "%s/%s" % (self._chemin_statut(), action), {}
        )
        self._journaliser(
            "%s demande sur %s (VMID %s)." % (libelle, self.server_id.name, self.vmid)
        )
        self.write({"last_synced_on": False})

    def action_start(self):
        """Démarrer la machine sur son serveur."""
        self._agir_sur_statut("start", "Démarrage")

    def action_stop(self):
        """Couper la machine immédiatement (hard stop)."""
        self._agir_sur_statut("stop", "Arrêt forcé")

    def action_shutdown(self):
        """Eteindre la machine proprement (ACPI)."""
        self._agir_sur_statut("shutdown", "Extinction")

    def action_reboot(self):
        """Redémarrer la machine proprement."""
        self._agir_sur_statut("reboot", "Redémarrage")
