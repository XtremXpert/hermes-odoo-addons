{
    "name": "DMS UX",
    "summary": "Drop files onto directories and act on many files at once.",
    "version": "20.0.1.0.0",
    "category": "Document Management",
    "license": "LGPL-3",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "author": "XtremXpert, Odoo Community Association (OCA)",
    "depends": ["dms"],
    "data": [
        "security/ir.access.csv",
        "wizard/dms_file_move_wizard_views.xml",
        "wizard/dms_file_tag_wizard_views.xml",
        "views/dms_file_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "dms_ux/static/src/js/directory_drop.esm.js",
            "dms_ux/static/src/js/directory_views.esm.js",
        ],
    },
    "installable": True,
    "application": False,
}
