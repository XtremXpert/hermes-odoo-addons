{
    "name": "Hermes — connexion aux interfaces des agents par Odoo",
    "summary": "Les tableaux de bord Hermes N1-N3 s'ouvrent avec la session Odoo d'un administrateur",
    "version": "20.0.1.0.0",
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "license": "AGPL-3",
    "depends": ["base", "web"],
    # No access rights: the codes are only read and written by the two routes, in sudo.
    "installable": True,
}
