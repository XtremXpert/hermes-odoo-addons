Aucune dépendance externe : le module ne déclare ni dépendance Python ni
binaire (`external_dependencies` absent) et s'installe comme un module Odoo
standard. Il dépend de `mail` et `hermes_n1_audit`, installés automatiquement.

Si `hermes_n2_support` ou `hermes_n3_infra` sont installés, leurs groupes
d'agent sont reconnus en plus ; sans eux, seuls les agents N1 le sont (les
références sont résolues avec `raise_if_not_found=False`). La tâche planifiée
d'expiration de présence est créée à l'installation : rien à lancer à la main.
