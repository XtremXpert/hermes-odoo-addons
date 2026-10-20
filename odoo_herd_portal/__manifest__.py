{
    "name": "Odoo Herd Portal",
    "version": "20.0.1.6.0",
    "category": "Administration/Kubernetes",
    "summary": "Client portal for an Odoo production and its staging: "
    "staging resync, human-confirmed promotion to production, new database requests",
    "author": "Bemade Inc., Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "license": "LGPL-3",
    "depends": [
        "odoo_herd",
        "portal",
        "auth_totp",
        "auth_totp_portal",
        "mail",
    ],
    "data": [
        "security/groups.xml",
        "security/ir.access.csv",
        "data/ir_sequence_data.xml",
        "data/ir_cron_data.xml",
        "data/portal_entry_data.xml",
        "views/k8s_odoo_instance_views.xml",
        "views/k8s_odoo_promotion_views.xml",
        "views/k8s_odoo_promotion_confirm_views.xml",
        "views/k8s_odoo_instance_request_views.xml",
        "views/portal_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "odoo_herd_portal/static/src/interactions/herd_portal_counters.js",
            "odoo_herd_portal/static/src/interactions/herd_new_database.js",
        ],
    },
    "installable": True,
}
