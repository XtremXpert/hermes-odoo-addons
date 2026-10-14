{
    "name": "Hermes — activité dans Discussion",
    "version": "20.0.1.2.0",
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "license": "AGPL-3",
    "depends": ["mail", "hermes_n1_audit"],
    "data": ["data/presence_cron.xml"],
    "assets": {
        "web.assets_backend": [
            "hermes_activity/static/src/activity.esm.js",
            "hermes_activity/static/src/activity.xml",
            "hermes_activity/static/src/approval.esm.js",
        ]
    },
    "installable": True,
}
