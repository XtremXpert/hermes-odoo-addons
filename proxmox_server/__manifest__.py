# Part of the proxmox_server Odoo module. See LICENSE for details.
{
    "name": "Proxmox : plateforme",
    "version": "20.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["proxmox_tenant", "mail"],
    "data": [
        "security/proxmox_server_groups.xml",
        "security/ir.access.csv",
        "views/proxmox_tenant_views.xml",
        "views/proxmox_menus.xml",
    ],
    "installable": True,
    "application": False,
}
