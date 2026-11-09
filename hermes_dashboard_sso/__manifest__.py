{
    "name": "Hermes — connexion aux interfaces des agents par Odoo",
    "summary": "Les tableaux de bord Hermes N1-N3 s'ouvrent avec la session Odoo d'un administrateur",
    "version": "20.0.1.0.0",
    "development_status": "Beta",
    "category": "Administration",
    "author": "Benoît Vézina, Diverse-Cité",
    "website": "https://github.com/XtremXpert/hermes-odoo-addons",
    "maintainers": ["XtremXpert"],
    "license": "AGPL-3",
    "depends": ["base", "web"],
    # Les codes ne sont lus et écrits que par les deux routes, en sudo. L'ACL
    # ne donne accès qu'au groupe technique (convention OCA : un modèle sans
    # ACL est un oubli, pas un choix).
    "data": ["security/ir.access.csv"],
    "installable": True,
}
