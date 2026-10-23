# Part of the voipms_sms Odoo module. See LICENSE for details.
{
    "name": "VoIP.ms SMS",
    "category": "Productivity",
    "summary": """Envoyer des SMS via l'API VoIP.ms""",
    "version": "20.0.1.0.1",
    "depends": ["base"],
    "data": [
        "security/voipms_sms_groups.xml",
        "security/ir.access.csv",
        "views/voipms_did_views.xml",
        "views/voipms_sms_out_views.xml",
        "views/voipms_sms_menus.xml",
        "views/res_config_settings_views.xml",
    ],
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "auto_install": False,
}
