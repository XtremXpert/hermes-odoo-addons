# Part of the proxmox_tenant Odoo module. See LICENSE for details.
"""Réglages Proxmox : URL du cluster, jeton API, perimetre par pool."""

from odoo import fields
from odoo import models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    proxmox_base_url = fields.Char(
        string="URL du serveur Proxmox",
        config_parameter="proxmox.base_url",
        help="https://pve.exemple.com:8006",
    )
    proxmox_api_token = fields.Char(
        string="Jeton API",
        config_parameter="proxmox.api_token",
        help="user@realm!tokenid=uuid — révocable côté Proxmox.",
    )
    proxmox_verify_ssl = fields.Boolean(
        string="Vérifier le certificat",
        config_parameter="proxmox.verify_ssl",
        default=True,
        help="Décocher pour un certificat autosigné.",
    )
    proxmox_allowed_pools = fields.Char(
        string="Pools du tenant",
        config_parameter="proxmox.allowed_pools",
        help="Séparés par des virgules. Vide : l'opérateur voit tout le cluster.",
    )
