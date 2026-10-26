# Part of the imap_client Odoo module. See LICENSE for details.
{
    "name": "Courriels IMAP",
    "version": "20.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["mail"],
    "data": [
        "security/imap_groups.xml",
        "security/ir.access.csv",
        "views/imap_reply_views.xml",
        "views/imap_message_views.xml",
        "views/imap_folder_views.xml",
        "views/imap_account_views.xml",
        "views/imap_menus.xml",
    ],
    "installable": True,
    "application": True,
}
