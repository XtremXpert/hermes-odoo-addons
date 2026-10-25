# Part of the wazo_phone Odoo module. See LICENSE for details.
{
    "name": "Téléphonie Wazo",
    "category": "Productivity",
    "summary": """Connecteur Wazo Platform : utilisateurs, extensions et journal d'appels""",
    "version": "20.0.4.0.0",
    # « mail » : note sur le contact et activité « appel manqué » du bouclage
    # d'appel, plus le bus Odoo des notifications (P3.3g).
    "depends": ["wazo_tenant", "web", "mail"],
    "data": [
        "views/wazo_dashboard_views.xml",
        "views/res_config_settings_views.xml",
        "views/wazo_menus.xml",
    ],
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "auto_install": False,
    "assets": {
        "web.assets_backend": [
            # Sans ordre explicite, Odoo trie les modules du paquet et place
            # wazo_phone avant « web » (« waz » < « web ») : nos fichiers
            # passeraient devant module_loader.js, qui définit odoo.define, et
            # le client web mourrait au chargement sans la moindre erreur côté
            # serveur. La directive « après le chargeur » ne dépend ni des noms
            # ni du tri.
            ("after", "web/static/src/module_loader.js", "wazo_phone/static/src/softphone/*.js"),
            ("after", "web/static/src/module_loader.js", "wazo_phone/static/src/dashboard/*.js"),
            ("after", "web/static/src/module_loader.js", "wazo_phone/static/src/phone/*.js"),
            "wazo_phone/static/src/softphone/wazo_softphone_templates.xml",
            "wazo_phone/static/src/softphone/wazo_softphone.scss",
            "wazo_phone/static/src/dashboard/wazo_dashboard_templates.xml",
        ],
        "wazo_phone.assets_sip": [
            "wazo_phone/static/lib/sip.js",
        ],
        # Bundle du SDK officiel Wazo (P3.3f), chargé à la demande
        # (``loadBundle``) : il ne pénalise pas le webclient tant que le
        # moteur SDK n'est pas sélectionné. Vendorisé enveloppé → ses
        # exports vivent sous ``window.WazoSDK``, pas sur la racine.
        "wazo_phone.assets_sdk": [
            "wazo_phone/static/lib/wazo-sdk.js",
        ],
    },
}
