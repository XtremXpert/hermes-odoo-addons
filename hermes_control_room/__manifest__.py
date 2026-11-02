# Part of the hermes_control_room Odoo module. See LICENSE for details.
{
    "name": "Hermes — Salle de contrôle",
    "version": "20.0.1.0.0",
    "license": "LGPL-3",
    "summary": "Tableau de bord d'exploitation : Proxmox, lu depuis les miroirs Odoo.",
    "depends": ["proxmox_tenant", "web"],
    "data": ["views/menus.xml"],
    "assets": {
        "web.assets_backend": [
            "hermes_control_room/static/src/dashboard/dashboard.scss",
            "hermes_control_room/static/src/dashboard/dashboard.esm.js",
            "hermes_control_room/static/src/dashboard/dashboard.xml",
        ],
    },
    "installable": True,
    "application": True,
}
