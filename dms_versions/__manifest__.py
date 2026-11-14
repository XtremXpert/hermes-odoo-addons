{
    "name": "DMS File Versions",
    "summary": "Keep and restore the history of every DMS file content change.",
    "version": "20.0.1.0.0",
    "category": "Document Management",
    "license": "LGPL-3",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "author": "XtremXpert, Odoo Community Association (OCA)",
    "depends": ["dms"],
    "data": [
        "security/ir.access.csv",
        "views/dms_file_version_views.xml",
        "views/dms_file_views.xml",
    ],
    "installable": True,
    "application": False,
}
