Pour utiliser ce module, il faut :

1. Disposer d'un cluster Kubernetes joignable et de son kubeconfig, et attribuer le
   groupe **K8s User** (lecture) ou **K8s Manager** (gestion complète) aux usagers.
2. Ouvrir _Odoo Herd_ > _Clusters_ et créer un cluster : nom, point d'accès
   (`api_endpoint`), `default_namespace`, et coller le kubeconfig dans l'onglet
   _Kubeconfig_. **Test Connection** écrit l'état de la connexion ; **Sync Instances**
   rapatrie les `OdooInstance` du cluster.
3. Ouvrir _Odoo Herd_ > _Odoo Instances_ pour la liste (phase, image courante,
   réplicas prêtes, URL). La fiche d'une instance propose **Open Instance**,
   **View Logs**, **Backup now**, **Upgrade**, **Reset to Current**,
   **Sync to Cluster** et **DELETE INSTANCE** ; une instance de staging a en plus
   **Refresh from Production**.
4. Créer une instance depuis la fiche d'un cluster avec **Create Instance** : modèle,
   cluster, nom, namespace, image, mot de passe administrateur, hôtes d'ingress et
   environnement, puis le mode d'initialisation (base neuve, restauration d'une
   instance, restauration d'une sauvegarde ou clonage d'une production).
5. Suivre les travaux dans _Odoo Herd_ > _Backup/Restore_ : _Backups_,
   _Restore Jobs_, _Upgrade Jobs_, _Staging Refresh Jobs_ et _Upload Backup_. La fiche
   d'une sauvegarde propose **Download** et **Restore**.
6. Lire l'état d'ensemble dans _Odoo Herd_ > _Dashboard_ (bascule
   _Auto-refresh (10s)_, bouton **Sync & Refresh**) : les cartes de cluster ouvrent
   **Instances**, **New** et **Backups**, et le bouton flèche relance la
   synchronisation.

Les modifications faites sur une fiche d'instance ne partent au cluster qu'avec
**Sync to Cluster**, qui n'envoie que les champs modifiés ; **Reset to Current** revient
aux valeurs du cluster.
