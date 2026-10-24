# Part of the wazo_tenant Odoo module. See LICENSE for details.
{
    "name": "Téléphonie Wazo — tenant",
    "category": "Productivity",
    "summary": """Exploitation d'un tenant Wazo : utilisateurs, postes, groupes, CDR""",
    "version": "20.0.3.0.0",
    "depends": ["base", "web", "mail"],
    "data": [
        "security/wazo_groups.xml",
        "security/ir.access.csv",
        "data/ir_cron.xml",
        "views/res_partner_views.xml",
        "views/wazo_user_views.xml",
        "views/wazo_ring_group_views.xml",
        "views/wazo_objects_views.xml",
        "views/res_users_wazo_views.xml",
        "wizards/wazo_context_inventory_views.xml",
        "views/wazo_cdr_views.xml",
        "views/res_config_settings_views.xml",
        "views/wazo_menus.xml",
        "views/wazo_tenant_dashboard_views.xml",
    ],
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "license": "LGPL-3",
    "assets": {
        "web.assets_backend": [
            # « wazo_tenant » se trie avant « web » (« waz » < « web ») :
            # sans directive d'ordre, nos fichiers passeraient devant
            # module_loader.js, qui définit odoo.define.
            ("after", "web/static/src/module_loader.js", "wazo_tenant/static/src/dashboard/*.js"),
            "wazo_tenant/static/src/dashboard/wazo_tenant_dashboard_templates.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
    "pre_init_hook": "adopt_wazo_phone_xmlids",
}
