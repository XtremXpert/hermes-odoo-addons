# Part of the proxmox_server Odoo module. See LICENSE for details.
"""Tenants Proxmox : création de pool, membres, suppression — client moqué."""

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestProxmoxTenant(TransactionCase):
    def setUp(self):
        super().setUp()
        self.serveur = self.env["proxmox.server"].create(
            {"name": "pve1", "url": "https://pve.test:8006", "api_token": "root@pam!odoo=aa-11"}
        )
        self.tenant = self.env["proxmox.tenant"].create(
            {"name": "diverse", "server_id": self.serveur.id, "pool_name": "diverse"}
        )

    def _client(self, appels, reponses=None):
        reponses = reponses or {}

        class Client:
            def _request(self, method, path, data=None):
                appels.append((method, path, data))
                return reponses.get((method, path), {})

        return lambda *a, **k: Client()

    def _patch(self, appels, reponses=None):
        return patch(
            "odoo.addons.proxmox_tenant.models.proxmox_server.ProxmoxClient",
            self._client(appels, reponses),
        )

    def test_creer_pool_poste_sur_le_serveur(self):
        """La création poste poolid + commentaire sur /pools."""
        appels = []
        with self._patch(appels):
            self.tenant.action_creer_pool()
        self.assertEqual(
            appels, [("POST", "/pools", {"poolid": "diverse", "comment": "tenant diverse"})]
        )
        self.assertTrue(self.tenant.remote_created)

    def test_supprimer_refuse_un_pool_non_vide(self):
        """Un pool qui a des membres ne se supprime pas."""
        reponses = {("GET", "/pools/diverse"): {"members": [{"vmid": 100}]}}
        with self._patch([], reponses), self.assertRaises(UserError):
            self.tenant.action_supprimer_pool()

    def test_creer_serveur_scope_le_tenant(self):
        """La fiche serveur du tenant borne la vue à son pool."""
        serveur = self.tenant.action_creer_serveur()
        self.assertEqual(serveur.allowed_pools, "diverse")
        self.assertEqual(serveur.url, self.serveur.url)
