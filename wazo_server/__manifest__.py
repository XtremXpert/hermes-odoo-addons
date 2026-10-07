# Part of the wazo_server Odoo module. See LICENSE for details.
{
    "name": "Téléphonie Wazo — serveur",
    "category": "Productivity",
    "summary": """Création et encadrement des tenants Wazo""",
    "version": "20.0.1.0.0",
    "depends": ["wazo_phone"],
    "data": [
        "security/ir.access.csv",
        "views/wazo_server_tenant_views.xml",
        "views/wazo_tenant_selection_views.xml",
        "views/wazo_server_menus.xml",
    ],
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "auto_install": False,
}
