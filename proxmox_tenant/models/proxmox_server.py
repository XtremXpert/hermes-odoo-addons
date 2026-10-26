# Part of the proxmox_tenant Odoo module. See LICENSE for details.
"""Serveur Proxmox : hote du cluster géré — plusieurs serveurs, un tenant chacun.

Un hote = une ligne ici : son URL, son jeton API, et les pools du tenant
qu'il faut voir. Le client API prend ses reglages de la fiche, pas des
parametres globaux — chaque serveur a sa cle.
"""

from odoo import api
from odoo import fields
from odoo import models

from ..services.proxmox_client import ProxmoxClient


class ProxmoxServer(models.Model):
    _name = "proxmox.server"
    _inherit = ["proxmox.sync.mixin"]
    _description = "Serveur Proxmox"
    _order = "name"

    name = fields.Char(string="Nom", required=True)
    url = fields.Char(
        string="URL", required=True, help="https://pve.exemple.com:8006"
    )
    api_token = fields.Char(
        string="Jeton API", required=True,
        help="user@realm!tokenid=uuid",
        groups="proxmox_tenant.group_proxmox_manager",
    )
    verify_ssl = fields.Boolean(string="Vérifier le certificat", default=True)
    allowed_pools = fields.Char(
        string="Pools du tenant",
        help="Séparés par des virgules. Vide : tout le serveur est visible.",
    )
    active = fields.Boolean(default=True)

    _proxmox_server_url_uniq = models.Constraint(
        "unique(url)", "Ce serveur est déjà déclaré."
    )

    def _client(self):
        """Le client API regle sur cette fiche."""
        self.ensure_one()
        return ProxmoxClient(
            self.env,
            base_url=self.url,
            api_token=self.api_token,
            verify_ssl=self.verify_ssl,
        )

    @api.model
    def _serveurs_actifs(self):
        return self.search([("active", "=", True)])
