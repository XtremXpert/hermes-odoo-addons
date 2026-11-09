# Part of the asterisk_ari Odoo module. See LICENSE for details.
{
    "name": "Téléphonie (Asterisk ARI)",
    "category": "Productivity",
    "summary": """Click-to-call et suivi d'appels via Asterisk ARI (FreePBX)""",
    "version": "20.0.1.0.0",
    "development_status": "Beta",
    "license": "LGPL-3",
    "author": "Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "maintainers": ["XtremXpert"],
    "depends": ["base"],
    "data": [
        "security/asterisk_ari_groups.xml",
        "security/ir.model.access.csv",
        "views/asterisk_call_views.xml",
        "views/asterisk_ari_menus.xml",
        "views/res_partner_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {},
    "application": True,
    "installable": True,
}
