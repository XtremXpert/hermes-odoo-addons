## Limites connues

- **Kubeconfig en clair** : `k8s.cluster.kubeconfig` est un champ `Text` stocké
  sans chiffrement dans la base ; il compte donc dans les sauvegardes et les
  clones (voir `readme/CONFIGURE.md`).
- **Dépendances Python hors Odoo** : `kubernetes`, `pyyaml`, `boto3` et
  `openupgradelib` sont déclarés dans `external_dependencies` et doivent être
  installés dans l'environnement Odoo ; le `post_init_hook` importe
  `openupgradelib`, donc une installation sans elle échoue.
- **Synchronisation automatique inactive par défaut** : la tâche
  `cron_k8s_sync_instances` (toutes les 15 minutes) porte `active = False` ;
  sans activation, la découverte des instances est manuelle.
- **Test dépendant d'un cluster réel** : plusieurs tests sont taggés
  `@tagged("-standard", "kube_cluster_present")` et ne s'exécutent pas sans un
  cluster Kubernetes joignable.
- **Identité de l'instance figée** : `name`, `cluster_id` et `namespace` sont
  `readonly` sur `k8s.odoo.instance` ; renommer ou déplacer une instance revient
  à créer une autre ressource.
- **Aucun écran de réglages** : pas de `res.config.settings` ; la configuration
  se pose sur les fiches (cluster, modèle, S3).
- **Webhooks facultatifs mais attendus** : sans webhook, l'état d'un travail est
  relu au bout de `POLL_DELAY = 2 min` par la tâche planifiée ; un travail dont
  la ressource n'a pas été créée après `CREATION_TIMEOUT = 15 min` est marqué en
  échec (« the Kubernetes job was never created »).
- **Point d'attention sur le `post_init_hook`** : `post_remove_old_module`
  interroge `openupgradelib` et désinstalle le module nommé `odoo_herd` s'il le
  voit installé — hérité de la reprise Bemade.
- **Dette de lint assumée** : `.pre-commit-config.yaml` exclut `odoo_herd` et
  `odoo_herd_portal` d'ESLint jusqu'à une PR dédiée.

## Pistes

- Retirer l'exclusion ESLint annoncée dans `.pre-commit-config.yaml` (« le temps
  d'une PR à part ») une fois le nettoyage JS fait.
