Aucune dépendance externe : le module ne déclare ni dépendance Python ni
binaire (`external_dependencies` absent) et s'installe comme un module Odoo
standard. Le client ARI n'utilise que `urllib` de la bibliothèque standard.

Le service Odoo doit pouvoir joindre l'API ARI — FreePBX l'expose sur
`http://<hôte>:8088/ari` — et présenter les identifiants Basic d'une
application ARI. Aucun ordre d'installation particulier : le module dépend de
`base`, installé avec Odoo.
