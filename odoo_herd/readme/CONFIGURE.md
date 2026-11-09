Le module n'a pas d'écran de réglages `res.config.settings` : la connexion et les
droits se posent sur les enregistrements.

1. **Groupes** : _K8s User_ (`odoo_herd.group_k8s_user`) lit clusters et instances ;
   _K8s Manager_ (`odoo_herd.group_k8s_manager`) implique le précédent et autorise les
   opérations et les menus de _Configuration_.
2. **Cluster** (_Odoo Herd_ > _Clusters_) : nom, point d'accès (`api_endpoint`),
   `default_namespace`, kubeconfig (onglet _Kubeconfig_), modèle d'instance par défaut,
   configuration S3 par défaut, URL de webhook et vérification TLS. Le kubeconfig est
   stocké en clair dans la base : il compte dans les sauvegardes et les clones.
3. **Configuration** (_Odoo Herd_ > _Configuration_, groupe gestionnaire) :
   _Instance Templates_ (image, `cluster_issuer`, taille et classe de stockage du
   filestore, mode d'initialisation par défaut) et _S3/MinIO Configs_ (secret
   d'identifiants, namespace).
4. **Tâches planifiées** : la synchronisation automatique des clusters est inactive
   par défaut (`Sync Kubernetes Odoo Instances`, toutes les 15 minutes) ; la
   vérification des travaux de l'opérateur (`Odoo Herd: read back operator jobs from
   the cluster`) est active toutes les 2 minutes, et l'exécution des sauvegardes
   planifiées toutes les heures.
5. **Dépendances Python** : `kubernetes`, `pyyaml`, `boto3` et `openupgradelib`
   doivent être installés dans l'environnement Odoo.
