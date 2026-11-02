# Part of the hermes_control_room Odoo module. See LICENSE for details.
"""Read-only snapshots for the control room.

Every figure comes from the local Proxmox mirrors synchronised by
``proxmox_tenant``; opening the dashboard never calls the Proxmox API. The age
of the snapshot is part of the payload on purpose: a dashboard that hides how
old its data is lies by omission.
"""

from odoo import api
from odoo import fields
from odoo import models

MEMORY_WARNING = 0.90
MEMORY_CRITICAL = 0.97


class ControlRoom(models.AbstractModel):
    _name = "control.room"
    _description = "Salle de contrôle — instantanés"

    @api.model
    def proxmox_snapshot(self):
        """Return the Proxmox picture as a plain dict, ready for the client."""
        servers = self.env["proxmox.server"].search([("active", "=", True)])
        nodes = self.env["proxmox.node"].search([("active", "=", True)])
        vms = self.env["proxmox.vm"].search([("active", "=", True)])

        running = vms.filtered(lambda vm: vm.status == "running")
        stopped = vms.filtered(lambda vm: vm.status == "stopped")
        paused = vms.filtered(lambda vm: vm.status == "paused")

        alerts = []
        for node in nodes:
            if node.status != "online":
                alerts.append({
                    "level": "critical",
                    "text": "%s : %s" % (node.name, node.status or "état inconnu"),
                })
                continue
            ratio = (node.mem_used / node.mem_max) if node.mem_max else 0.0
            if ratio >= MEMORY_CRITICAL:
                alerts.append({
                    "level": "critical",
                    "text": "%s : mémoire à %d %%" % (node.name, ratio * 100),
                })
            elif ratio >= MEMORY_WARNING:
                alerts.append({
                    "level": "warning",
                    "text": "%s : mémoire à %d %%" % (node.name, ratio * 100),
                })
        for vm in stopped:
            alerts.append({"level": "info", "text": "VM arrêtée : %s (%s)" % (vm.name, vm.vmid)})

        stamped = [r.last_synced_on for r in (nodes | vms) if r.last_synced_on]
        memory_used = sum(nodes.mapped("mem_used"))
        memory_max = sum(nodes.mapped("mem_max"))

        return {
            "generated_at": fields.Datetime.to_string(fields.Datetime.now()),
            "synced_at": fields.Datetime.to_string(max(stamped)) if stamped else False,
            "totals": {
                "servers": len(servers),
                "nodes": len(nodes),
                "vms": len(vms),
                "running": len(running),
                "stopped": len(stopped),
                "paused": len(paused),
                "memory_used": memory_used,
                "memory_max": memory_max,
            },
            "nodes": [
                {
                    "name": node.name,
                    "status": node.status,
                    "cpu": round(node.cpu * 100, 1),
                    "memory_ratio": (
                        round(node.mem_used / node.mem_max * 100, 1) if node.mem_max else 0.0
                    ),
                }
                for node in nodes.sorted("name")
            ],
            "alerts": alerts,
        }
