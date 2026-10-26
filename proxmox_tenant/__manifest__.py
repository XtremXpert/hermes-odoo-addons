# Part of the proxmox_tenant Odoo module. See LICENSE for details.
{
    "name": "Proxmox — tenant",
    "version": "20.0.1.0.0",
    "category": "Services",
    "summary": "Cluster Proxmox VE : noeuds, machines, pools, stockage — perimetre par pool",
    "author": "XtremXpert",
    "license": "LGPL-3",
    "depends": ["base", "mail"],
    "data": [
        "security/proxmox_groups.xml",
        "security/ir.access.csv",
        "views/proxmox_server_views.xml",
        "views/proxmox_node_views.xml",
        "views/proxmox_vm_views.xml",
        "views/proxmox_pool_views.xml",
        "views/proxmox_storage_views.xml",
        "views/proxmox_menus.xml",
    ],
    "application": True,
    "installable": True,
}
