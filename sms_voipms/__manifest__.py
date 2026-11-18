# Part of the sms_voipms Odoo module. See LICENSE for details.
{
    "name": "SMS via VoIP.ms",
    "category": "Productivity",
    "summary": "Envoyer les SMS d'Odoo par l'API VoIP.ms",
    "version": "20.0.1.0.0",
    "development_status": "Beta",
    "depends": ["sms", "voipms_sms"],
    "data": [
        "security/ir.access.csv",
        "views/res_config_settings_views.xml",
        "views/sms_sms_views.xml",
    ],
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "maintainers": ["XtremXpert"],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
}
