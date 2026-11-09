Quatre dépendances Python hors Odoo sont obligatoires avant l'installation :
`kubernetes`, `pyyaml`, `boto3` et `openupgradelib`. Elles sont déclarées dans
`external_dependencies` du manifeste et reprises dans `requirements.txt` du
dépôt ; `openupgradelib` est en plus importée par le `post_init_hook`
`post_remove_old_module`, sans quoi l'installation échoue.

Le module dépend de `base`, `web` et `mail` et s'installe comme un module Odoo
standard. Un cluster Kubernetes joignable et son kubeconfig sont nécessaires à
l'usage, pas à l'installation ; la connexion se règle ensuite sur la fiche du
cluster.
