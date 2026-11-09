Aucune dépendance externe : le module ne déclare ni dépendance Python ni
binaire (`external_dependencies` absent) et s'installe comme un module Odoo
standard. Il dépend de `base` et `web`.

Le module doit être installé sur l'hôte qui sert les tableaux de bord : l'URL de
retour acceptée est dérivée de l'hôte de la requête
(`https://<cet hôte>/hermes/<niveau>/auth/callback`). Sur un autre hôte,
l'autorisation est refusée (400). Aucun ordre d'installation particulier.
