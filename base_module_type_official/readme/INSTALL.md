Aucune dépendance externe : le module ne déclare ni dépendance Python ni
binaire (`external_dependencies` absent) et s'installe comme un module Odoo
standard. Il dépend de `base_import_module`, installé automatiquement avec lui.

Aucun ordre manuel et aucune migration : la correction s'exécute à chaque
démarrage, sur les lignes dont `module_type` est NULL.
