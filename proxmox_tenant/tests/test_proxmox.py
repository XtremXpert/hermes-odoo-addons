# Part of the proxmox_tenant Odoo module. See LICENSE for details.
"""Proxmox : client moqué, périmètre par pool, actions des machines."""

from unittest.mock import patch

from odoo.tests.common import TransactionCase


def _cliente_simule(reponses):
    """Un ProxmoxClient factice : les réponses par chemin d'API."""

    class ClientSimule:
        def __init__(self, env, **kw):
            pass

        def _request(self, method, path, data=None):
            if isinstance(reponses, Exception):
                raise reponses
            if (method, path) in reponses:
                return reponses[(method, path)]
            for (m, p), rep in reponses.items():
                if method == m and path.startswith(p):
                    return rep
            return []

    return ClientSimule


RESSOURCES = [
    {
        "vmid": 100,
        "name": "web01",
        "node": "pve1",
        "type": "qemu",
        "status": "running",
        "pool": "diverse",
        "maxcpu": 2,
        "maxmem": 4096,
        "maxdisk": 32212254720,
        "uptime": 3600,
    },
    {
        "vmid": 101,
        "name": "bdd01",
        "node": "pve1",
        "type": "lxc",
        "status": "stopped",
        "pool": "mac",
        "maxcpu": 1,
        "maxmem": 2048,
        "maxdisk": 10737418240,
        "uptime": 0,
    },
]

NOEUDS = [
    {
        "node": "pve1",
        "status": "online",
        "uptime": 9999,
        "cpu": 0.2,
        "mem": 1024,
        "maxmem": 8192,
        "disk": 1024,
        "maxdisk": 4096,
    },
]

POOLS = [
    {"poolid": "diverse", "comment": "Diverse-Cité", "members": [{"vmid": 100}]},
    {"poolid": "mac", "comment": "Mac", "members": [{"vmid": 101}]},
]


class TestProxmoxSync(TransactionCase):
    """La synchronisation rapatrie ce que le cluster déclare, au périmètre."""

    def setUp(self):
        super().setUp()
        self.serveur = self.env["proxmox.server"].create(
            {"name": "pve1", "url": "https://pve.test:8006",
             "api_token": "root@pam!odoo=aa-11"}
        )

    def test_les_vms_du_perimetre_seulement(self):
        """Un pool autorisé borne ce que la sync rapatrie."""
        self.serveur.allowed_pools = "diverse"
        reponses = {("GET", "/cluster/resources?type=vm"): RESSOURCES}
        with patch(
            "odoo.addons.proxmox_tenant.models.proxmox_server.ProxmoxClient",
            _cliente_simule(reponses),
        ):
            self.env["proxmox.vm"]._sync_all_from_proxmox()
        machines = self.env["proxmox.vm"].search([])
        self.assertEqual(len(machines), 1)
        self.assertEqual(machines.vmid, 100)
        self.assertEqual(machines.status, "running")

    def test_sans_perimetre_tout_rapatrie(self):
        """Un paramètre vide = opérateur : tout le cluster est visible."""
        reponses = {("GET", "/cluster/resources?type=vm"): RESSOURCES}
        with patch(
            "odoo.addons.proxmox_tenant.models.proxmox_server.ProxmoxClient",
            _cliente_simule(reponses),
        ):
            self.env["proxmox.vm"]._sync_all_from_proxmox()
        self.assertEqual(self.env["proxmox.vm"].search_count([]), 2)

    def test_noeuds_et_pools(self):
        """Noeuds et pools se rapatrient avec le même contrat."""
        self.serveur.allowed_pools = "diverse"
        reponses = {
            ("GET", "/cluster/resources?type=node"): NOEUDS,
            ("GET", "/pools"): POOLS,
        }
        with (
            patch(
                "odoo.addons.proxmox_tenant.models.proxmox_server.ProxmoxClient",
                _cliente_simule(reponses),
            ),
            patch(
                "odoo.addons.proxmox_tenant.models.proxmox_server.ProxmoxClient",
                _cliente_simule(reponses),
            ),
        ):
            self.env["proxmox.node"]._sync_all_from_proxmox()
            self.env["proxmox.pool"]._sync_all_from_proxmox()
        self.assertEqual(self.env["proxmox.node"].search_count([]), 1)
        pools = self.env["proxmox.pool"].search([])
        self.assertEqual([p.name for p in pools], ["diverse"])

    def test_action_start_poste_sur_le_noeud(self):
        """Un démarrage poste /status/start sur le bon noeud."""
        machine = self.env["proxmox.vm"].create(
            {
                "vmid": 100,
                "name": "web01",
                "node": "pve1",
                "machine_type": "qemu",
                "status": "stopped",
                "server_id": self.serveur.id,
            }
        )
        appels = []

        class Client:
            def _request(self, method, path, data=None):
                appels.append((method, path))
                return []

        with patch(
            "odoo.addons.proxmox_tenant.models.proxmox_server.ProxmoxClient",
            lambda *args, **kwargs: Client(),
        ):
            machine.action_start()
        self.assertEqual(appels, [("POST", "/nodes/pve1/qemu/100/status/start")])
