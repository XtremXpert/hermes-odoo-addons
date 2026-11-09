Pour utiliser ce module, il faut :

1. Disposer d'au moins un serveur Proxmox synchronisé par `proxmox_tenant` (_Proxmox_ >
   _Serveurs_) : sans miroir local, le tableau n'a rien à montrer.
2. Pour la partie Kubernetes, avoir déclaré au moins un cluster dans Odoo Herd : les
   clusters et leurs kubeconfigs sont lus dans `k8s.cluster`.
3. Attribuer à l'usager le groupe **Proxmox — Gestionnaire** (ou un groupe qui
   l'implique) : le menu est réservé à ce groupe.
4. Ouvrir _Salle de contrôle_ > _Proxmox_.

Le tableau se rafraîchit toutes les 60 secondes ; le bouton _Rafraîchir_ force la
relecture. Le bandeau indique la date de la dernière synchronisation Proxmox, ou
« Aucune synchronisation enregistrée ».

Les cartes résument le nombre de serveurs, de nœuds et de machines, les machines en
fonction et arrêtées, et la mémoire utilisée sur la mémoire totale. La table des nœuds
donne l'état, le CPU et la mémoire de chacun ; la table Kubernetes donne, par cluster,
la joignabilité, les nœuds prêts et les déploiements indisponibles, avec le détail de
l'erreur si le cluster ne répond pas.
