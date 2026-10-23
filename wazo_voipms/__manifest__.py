# Part of the wazo_voipms Odoo module. See LICENSE for details.
{
    "name": "Pont Wazo ↔ VoIP.ms",
    "category": "Productivity",
    "summary": """Trunk SIP VoIP.ms pour Wazo : appels sortants et routage des DIDs""",
    "version": "20.0.1.0.0",
    "depends": ["wazo_tenant", "voipms_sms"],
    "data": [
        "security/ir.access.csv",
        "views/wazo_voipms_trunk_views.xml",
        "views/voipms_did_views.xml",
        "views/wazo_voipms_menus.xml",
    ],
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "license": "LGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
}
