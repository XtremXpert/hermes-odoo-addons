Un seul groupe est ajouté : **Proxmox — Opérateur de plateforme**, visible dans l'onglet
_Droits d'accès_ de la fiche usager. Il implique le groupe **Proxmox — Gestionnaire** de
`proxmox_tenant` : un opérateur de plateforme gère donc aussi les fiches serveurs,
nœuds, machines, pools et stockages.

La connexion au cluster n'est pas réglée ici : elle vient de la fiche serveur choisie
sur le tenant (_Proxmox_ > _Serveurs_), donc de l'URL et du jeton API portés par
`proxmox.server`. Le module n'ajoute ni écran de réglages, ni paramètre système.
