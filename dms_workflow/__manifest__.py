{
    "name": "DMS Document Requests",
    "summary": "Request a document from someone and track it to the upload.",
    "version": "20.0.1.0.0",
    "category": "Document Management",
    "license": "LGPL-3",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "author": "XtremXpert, Odoo Community Association (OCA)",
    "depends": ["dms", "mail"],
    "data": [
        "security/ir.access.csv",
        "views/dms_file_request_views.xml",
        "views/dms_file_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
}
