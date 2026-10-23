# Part of the mailcow Odoo module. See LICENSE for details.
{
    "name": "Mailcow",
    "category": "Productivity",
    "summary": """Côté usager de Mailcow : vue d'ensemble du serveur""",
    "version": "20.0.1.0.0",
    "depends": ["mailcow_tenant"],
    "data": [
        "views/mailcow_dashboard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            # Sans ordre explicite, Odoo trie les modules du paquet et place
            # mailcow avant « web » (« mai » < « web ») : nos fichiers
            # passeraient devant module_loader.js, qui définit odoo.define, et
            # le client web mourrait au chargement sans la moindre erreur côté
            # serveur. La directive « après le chargeur » ne dépend ni des noms
            # ni du tri. Même recette que dans wazo_phone.
            ("after", "web/static/src/module_loader.js", "mailcow/static/src/dashboard/*.js"),
            "mailcow/static/src/dashboard/*.xml",
        ],
    },
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "auto_install": False,
    "pre_init_hook": "adopt_dashboard_xmlids",
}
