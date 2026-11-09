Aucune dépendance externe : le module ne déclare ni dépendance Python ni
binaire (`external_dependencies` absent) et s'installe comme un module Odoo
standard. Il dépend de `hermes_n1_audit` et `website`, installés
automatiquement ; l'installer après `website`, comme la dépendance l'impose.

Aucune migration ni script à lancer. Le module n'ajoute ni menu ni vue : son
effet se voit dans `hermes.n1.change` et sur les pages du site.
