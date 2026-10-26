# Part of the proxmox_server Odoo module. See LICENSE for details.
"""Tenant Proxmox : le pool d'un client sur un serveur donné.

Côté plateforme, un tenant = un pool Proxmox : le périmètre que le tenant
pourra voir et piloter. La fiche le crée sur le serveur (POST /pools) —
le module ``proxmox_tenant`` des instances du tenant le déclare ensuite
dans ``proxmox.server.allowed_pools`` pour en borner la vue.
"""

from odoo import fields
from odoo import models
from odoo.exceptions import AccessError
from odoo.exceptions import UserError


class ProxmoxTenant(models.Model):
    _name = "proxmox.tenant"
    _inherit = ["mail.thread"]
    _description = "Tenant Proxmox"
    _order = "name"

    name = fields.Char(string="Tenant", required=True)
    server_id = fields.Many2one(
        "proxmox.server", string="Serveur", required=True, ondelete="restrict"
    )
    pool_name = fields.Char(
        string="Pool",
        required=True,
        help="Identifiant du pool créé sur le serveur (lettres, tirets, traits bas).",
    )
    remote_created = fields.Boolean(string="Créé sur le serveur", readonly=True, default=False)
    members = fields.Integer(string="Membres", readonly=True)

    _proxmox_tenant_pool_uniq = models.Constraint(
        "unique(server_id, pool_name)", "Ce pool existe déjà sur ce serveur."
    )

    def _exiger(self):
        if self.env.su or self.env.user.has_group("proxmox_tenant.group_proxmox_manager"):
            return
        raise AccessError(self.env._("Action Proxmox réservée aux gestionnaires."))

    def action_creer_pool(self):
        """Créer le pool du tenant sur le serveur (POST /pools)."""
        self._exiger()
        for tenant in self:
            if tenant.remote_created:
                continue
            tenant.server_id._client()._request(
                "POST",
                "/pools",
                {"poolid": tenant.pool_name, "comment": "tenant %s" % tenant.name},
            )
            tenant.write({"remote_created": True})
            tenant.message_post(
                body=self.env._(
                    "Pool « %s » créé sur %s.",
                    tenant.pool_name, tenant.server_id.name,
                ),
                subtype_xmlid="mail.mt_note",
            )

    def action_lire_membres(self):
        """Relire le nombre de membres du pool depuis le serveur."""
        self._exiger()
        for tenant in self:
            entree = tenant.server_id._client()._request("GET", "/pools/%s" % tenant.pool_name)
            membres = len((entree or {}).get("members") or [])
            tenant.write({"members": membres, "remote_created": True})

    def action_supprimer_pool(self):
        """Supprimer le pool du tenant sur le serveur — jamais ses membres."""
        self._exiger()
        for tenant in self:
            entree = tenant.server_id._client()._request("GET", "/pools/%s" % tenant.pool_name)
            if (entree or {}).get("members"):
                raise UserError(
                    self.env._(
                        "Le pool « %s » n'est pas vide — retirez ses membres "
                        "avant de le supprimer.",
                        tenant.pool_name,
                    )
                )
            tenant.server_id._client()._request("DELETE", "/pools/%s" % tenant.pool_name)
            tenant.write({"remote_created": False})
            tenant.message_post(
                body=self.env._(
                    "Pool « %s » supprimé de %s.",
                    tenant.pool_name, tenant.server_id.name,
                ),
                subtype_xmlid="mail.mt_note",
            )

    def action_creer_serveur(self):
        """Créer la fiche hote Proxmox (proxmox.server) du tenant."""
        self._exiger()
        self.ensure_one()
        serveur = (
            self.env["proxmox.server"]
            .sudo()
            .create(
                {
                    "name": "%s / %s" % (self.server_id.name, self.pool_name),
                    "url": self.server_id.url,
                    "api_token": self.server_id.api_token,
                    "allowed_pools": self.pool_name,
                }
            )
        )
        self.message_post(
            body=self.env._(
                "Fiche serveur du tenant créée : %s (périmètre : %s).",
                serveur.name,
                self.pool_name,
            ),
            subtype_xmlid="mail.mt_note",
        )
        return serveur
