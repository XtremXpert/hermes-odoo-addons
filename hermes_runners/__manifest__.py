# Part of the hermes_runners Odoo module. See LICENSE for details.
{
    "name": "Hermes — Runners",
    "version": "20.0.1.0.0",
    "development_status": "Beta",
    "category": "Administration",
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "maintainers": ["XtremXpert"],
    "license": "LGPL-3",
    "summary": "État des runners GitHub Actions auto-hébergés (ARC), lu depuis les clusters.",
    "depends": ["odoo_herd", "web"],
    "data": ["views/menus.xml"],
    "assets": {
        "web.assets_backend": [
            "hermes_runners/static/src/dashboard/dashboard.scss",
            "hermes_runners/static/src/dashboard/dashboard.esm.js",
            "hermes_runners/static/src/dashboard/dashboard.xml",
        ],
    },
    "installable": True,
    "application": True,
}
