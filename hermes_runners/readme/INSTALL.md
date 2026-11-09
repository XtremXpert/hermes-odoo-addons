Aucune dépendance déclarée dans le manifeste, mais le module importe
`kubernetes` au chargement (`from kubernetes import client`). Cette
bibliothèque est déclarée par `odoo_herd` (`external_dependencies.python`), dont
le module dépend : elle est donc installée avec lui. L'environnement Odoo doit
fournir `kubernetes`, sinon le chargement du module échoue.

Dépend de `odoo_herd` et `web`, installés automatiquement ; aucun ordre manuel.
Sans cluster actif déclaré dans Odoo Herd, le tableau s'ouvre mais ne montre
aucun runner.
