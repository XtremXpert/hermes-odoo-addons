## Limites connues

- **Pas de temps réel** : la synchronisation part de `web_search_read`, bornée à
  `RAFRAICHISSEMENT_MIN_S = 60` secondes par objet. L'état affiché peut avoir
  jusqu'à une minute de retard, et il n'existe ni webhook ni tâche planifiée.
- **Serveur injoignable = état périmé sans alerte à l'écran** :
  `_rafraichir_si_obsolete` journalise l'échec (`_logger.warning`) et laisse le
  dernier état connu ; l'utilisateur ne voit pas que sa copie date.
- **`allowed_pools` ne filtre pas tout** : le périmètre s'applique aux pools et
  aux machines (`proxmox_pool`, `proxmox_vm`), pas aux nœuds ni aux stockages,
  qui sont rapatriés pour tout le serveur.
- **Champs distants en lecture seule** : noms, états, tailles et types sont
  `readonly` ; on ne corrige pas une fiche localement. Seules les actions de
  statut d'une machine sont possibles.
- **Disparition non destructive** : un objet absent du serveur passe à
  `active = False`, il n'est pas supprimé.
- **Jeton API en clair** : `proxmox.server.api_token` est un `Char`, affiché en
  `password` dans la vue et réservé au groupe gestionnaire, mais stocké sans
  chiffrement dans la base.
- **Statut `Beta`** : `development_status` vaut `Beta`.

## Pistes

Aucune piste n'est consignée : le code ne porte aucun marqueur de travail en attente.
