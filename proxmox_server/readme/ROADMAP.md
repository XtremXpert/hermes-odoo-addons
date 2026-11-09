## Limites connues

- **État distant en lecture seule** : `remote_created` et `members` sont
  `readonly` ; l'état du pool se constate par *Créer le pool* / *Relire les
  membres*, jamais en éditant la fiche.
- **Suppression refusée sur un pool non vide** : le module ne supprime jamais
  les membres d'un pool ; il faut les retirer d'abord.
- **Aucune relecture automatique** : contrairement à `proxmox_tenant`, le module
  n'a ni tâche planifiée ni rafraîchissement à l'ouverture ; le nombre de membres
  n'est à jour qu'après *Relire les membres*.
- **Jeton dupliqué** : `action_creer_serveur` recopie `url` et `api_token` du
  serveur de plateforme dans une fiche `proxmox.server` ; le secret existe alors
  dans deux fiches.
- **Un pool par serveur** : contrainte `unique(server_id, pool_name)`.
- **Statut `Beta`** : `development_status` vaut `Beta`.

## Pistes

Aucune piste n'est consignée : le code ne porte aucun marqueur de travail en attente.
