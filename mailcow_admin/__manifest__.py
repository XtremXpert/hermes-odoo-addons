# Part of the mailcow_admin Odoo module. See LICENSE for details.
{
    "name": "Mailcow Admin",
    "category": "Productivity",
    "summary": """Administer un serveur Mailcow depuis Odoo""",
    "version": "20.0.2.1.0",
    "depends": ["base", "mail"],
    "data": [
        "security/mailcow_admin_groups.xml",
        "security/ir.access.csv",
        "views/mailcow_email_address_views.xml",
        "views/mailcow_domain_views.xml",
        "views/mailcow_mailbox_views.xml",
        "wizards/mailcow_app_password_wizard_views.xml",
        "views/mailcow_alias_views.xml",
        "views/res_config_settings_views.xml",
        "views/mailcow_admin_menus.xml",
        "views/mailcow_dashboard_views.xml",
        "views/mailcow_sync_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            # Sans ordre explicite, Odoo trie les modules du paquet et place
            # mailcow_admin avant « web » (« mai » < « web ») : nos fichiers
            # passeraient devant module_loader.js, qui définit odoo.define, et
            # le client web mourrait au chargement sans la moindre erreur côté
            # serveur. La directive « après le chargeur » ne dépend ni des noms
            # ni du tri. Même recette que dans wazo_phone.
            ("after", "web/static/src/module_loader.js", "mailcow_admin/static/src/dashboard/*.js"),
            "mailcow_admin/static/src/dashboard/*.xml",
        ],
    },
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "auto_install": False,
}
