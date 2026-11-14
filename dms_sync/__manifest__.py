{
    "name": "DMS Sync",
    "summary": "Per-device sync scope for the DMS desktop client: Odoo decides what syncs.",
    "version": "20.0.1.0.0",
    "category": "Document Management",
    "license": "LGPL-3",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "author": "XtremXpert, Odoo Community Association (OCA)",
    "depends": ["dms"],
    "data": [
        "security/ir.access.csv",
        "views/dms_sync_device_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
}
