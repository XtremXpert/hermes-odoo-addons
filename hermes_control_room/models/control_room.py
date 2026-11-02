# Part of the hermes_control_room Odoo module. See LICENSE for details.
"""Read-only snapshots for the control room.

Every figure comes from the local Proxmox mirrors synchronised by
``proxmox_tenant``; opening the dashboard never calls the Proxmox API. The age
of the snapshot is part of the payload on purpose: a dashboard that hides how
old its data is lies by omission.
"""

from kubernetes import client

from odoo import api
from odoo import fields
from odoo import models


def summarize_kubernetes(nodes, deployments):
    """Pure aggregation, kept out of the API call so it can be tested alone."""
    ready = [node for node in nodes if node["ready"]]
    unavailable = [
        "%s/%s" % (item["namespace"], item["name"])
        for item in deployments
        if item["desired"] and item["ready"] < item["desired"]
    ]
    return {
        "nodes": nodes,
        "nodes_total": len(nodes),
        "nodes_ready": len(ready),
        "deployments_total": len(deployments),
        "deployments_unavailable": len(unavailable),
        "unavailable": sorted(unavailable)[:20],
    }


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
                alerts.append(
                    {
                        "level": "critical",
                        "text": "%s : %s" % (node.name, node.status or "état inconnu"),
                    }
                )
                continue
            ratio = (node.mem_used / node.mem_max) if node.mem_max else 0.0
            if ratio >= MEMORY_CRITICAL:
                alerts.append(
                    {
                        "level": "critical",
                        "text": "%s : mémoire à %d %%" % (node.name, ratio * 100),
                    }
                )
            elif ratio >= MEMORY_WARNING:
                alerts.append(
                    {
                        "level": "warning",
                        "text": "%s : mémoire à %d %%" % (node.name, ratio * 100),
                    }
                )
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

    @api.model
    def kubernetes_snapshot(self):
        """Read nodes and deployments from the clusters the herd already knows.

        The herd stores a kubeconfig per cluster and knows how to build a client
        from it; reusing that is safer than inventing a second credential path.
        A cluster that cannot be reached is reported as such, not hidden.
        """
        clusters = self.env["k8s.cluster"].search([])
        payload = []
        for cluster in clusters:
            entry = {
                "name": cluster.name,
                "reachable": False,
                "error": False,
                "nodes": [],
                "deployments": [],
            }
            try:
                api_client = cluster._get_k8s_client()
                core = client.CoreV1Api(api_client)
                apps = client.AppsV1Api(api_client)
                nodes = [
                    {
                        "name": node.metadata.name,
                        "ready": any(
                            condition.type == "Ready" and condition.status == "True"
                            for condition in (node.status.conditions or [])
                        ),
                    }
                    for node in core.list_node().items
                ]
                deployments = [
                    {
                        "namespace": item.metadata.namespace,
                        "name": item.metadata.name,
                        "ready": item.status.ready_replicas or 0,
                        "desired": item.spec.replicas or 0,
                    }
                    for item in apps.list_deployment_for_all_namespaces().items
                ]
                entry.update(summarize_kubernetes(nodes, deployments))
                entry["reachable"] = True
            except Exception as error:  # noqa: BLE001 - one bad cluster must not hide the others
                entry["error"] = str(error)[:200]
            payload.append(entry)
        return {
            "generated_at": fields.Datetime.to_string(fields.Datetime.now()),
            "clusters": payload,
            "totals": {
                "clusters": len(payload),
                "reachable": len([entry for entry in payload if entry["reachable"]]),
                "nodes": sum(entry["nodes_total"] for entry in payload if entry["reachable"]),
                "nodes_ready": sum(entry["nodes_ready"] for entry in payload if entry["reachable"]),
                "deployments": sum(
                    entry["deployments_total"] for entry in payload if entry["reachable"]
                ),
                "unavailable": sum(
                    entry["deployments_unavailable"] for entry in payload if entry["reachable"]
                ),
            },
        }
