Côté plateforme, le module crée et suit les tenants Proxmox : un tenant est un pool du
cluster, sur un serveur donné.

Depuis la fiche du tenant, _Créer le pool_ poste le pool et son commentaire sur l'API du
serveur, _Relire les membres_ rafraîchit le nombre de machines du pool, et _Supprimer le
pool_ le retire du serveur — à condition qu'il soit vide, car le module ne supprime
jamais ses membres. _Fiche serveur du tenant_ crée la fiche `proxmox.server`
correspondante, bornée à ce pool, que l'instance du tenant utilisera.

Toutes les opérations sont notées dans le fil de la fiche du tenant. Le module ajoute
son entrée sous le menu _Proxmox_ fourni par `proxmox_tenant`, et son accès est réservé
au groupe **Proxmox — Opérateur de plateforme**.
