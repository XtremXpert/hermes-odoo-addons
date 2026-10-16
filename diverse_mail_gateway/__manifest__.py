# Copyright (C) 2026 Bemade Inc.
# Copyright (C) 2026 Benoît Vézina, Diverse-Cité
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Mail Gateway — point d'entrée des courriels entrants",
    "version": "20.0.1.0.0",
    "category": "Tools",
    "summary": (
        "Point d'entrée HTTP authentifié par jeton qui pousse le courriel brut "
        "dans Odoo, sans compte utilisateur."
    ),
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "license": "AGPL-3",
    "depends": [
        "base",
        "mail",
    ],
    "data": [
        "security/security.xml",
        "security/ir.access.csv",
        "views/wizard_views.xml",
        "views/token_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
