Pour utiliser ce module, il faut :

1. Attribuer le groupe **Proxmox — Opérateur de plateforme** aux usagers de la
   plateforme, dans l'onglet _Droits d'accès_ de la fiche usager.
2. Disposer d'au moins une fiche serveur dans _Proxmox_ > _Serveurs_ (`proxmox_tenant`)
   : elle porte l'URL et le jeton API utilisés par les appels.
3. Ouvrir _Proxmox_ > _Tenants_ et créer un tenant : nom, serveur Proxmox et identifiant
   du pool.
4. Sur la fiche, cliquer _Créer le pool_ : le pool et son commentaire sont créés sur le
   serveur ; _Relire les membres_ affiche ensuite le nombre de machines qu'il contient.
5. Cliquer _Fiche serveur du tenant_ pour créer la fiche `proxmox.server` bornée à ce
   pool : c'est elle que l'instance du tenant déclarera pour ne voir que son périmètre.
6. _Supprimer le pool_ retire le pool du serveur ; l'opération est refusée tant que le
   pool n'est pas vide.

Chaque geste est journalisé dans le fil de la fiche du tenant.
