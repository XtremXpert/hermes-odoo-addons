# Part of the wazo_server Odoo module. See LICENSE for details.
{
    "name": "Téléphonie Wazo — serveur",
    "category": "Productivity",
    "summary": """Création et encadrement des tenants Wazo""",
    "version": "20.0.2.0.0",
    # « wazo_voipms » : le tableau de bord de l'exploitant lit l'état du
    # pont (trunk, DIDs). « web » : le tableau de bord importe
    # @web/@odoo/owl, et le tri des modules place wazo_server avant
    # « web » (« waz » < « web ») — d'où la directive d'ordre dans les
    # actifs, sans laquelle nos fichiers passeraient devant
    # module_loader.js et le client web mourrait sans un bruit.
    "depends": ["wazo_tenant", "wazo_voipms", "web"],
    "data": [
        "security/ir.access.csv",
        "views/wazo_server_tenant_views.xml",
        "views/wazo_tenant_selection_views.xml",
        "views/wazo_server_menus.xml",
        "views/wazo_server_dashboard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            ("after", "web/static/src/module_loader.js", "wazo_server/static/src/dashboard/*.js"),
            "wazo_server/static/src/dashboard/wazo_server_dashboard_templates.xml",
        ],
    },
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "auto_install": False,
}
