# Part of the proxmox_server Odoo module. See LICENSE for details.
{
    "name": "Proxmox : plateforme",
    "summary": "Plateforme Proxmox VE : cycle de vie des tenants",
    "version": "20.0.1.0.0",
    "development_status": "Beta",
    "category": "Services",
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "maintainers": ["XtremXpert"],
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
