Aucune dépendance déclarée dans le manifeste, mais le module importe
`kubernetes` au chargement (`from kubernetes import client`). Cette
bibliothèque est déclarée par `odoo_herd` (`external_dependencies.python`), dont
le module dépend : elle est donc installée avec lui. L'environnement Odoo doit
fournir `kubernetes`, sinon le chargement du module échoue.

Dépend de `proxmox_tenant`, `odoo_herd` et `web`, installés automatiquement ;
aucun ordre manuel. Sans serveur Proxmox synchronisé ni cluster déclaré, le
tableau s'ouvre mais n'a rien à montrer.
