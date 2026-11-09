## Limites connues

- **Journal d'appels non temps réel** : la tâche `ir_cron_wazo_cdr_sync` est
  déclarée **inactive par défaut** (`data/ir_cron.xml`), et la synchronisation
  lit par défaut les 24 dernières heures. Sans activation, seul le bouton manuel
  alimente le journal.
- **Synchronisation plafonnée** : `PER_PAGE = 200` et `MAX_PAGES = 50` bornent
  une passe à 10 000 entrées ; au-delà, les pages suivantes ne sont pas lues.
- **Écritures distantes non transactionnelles** : le flux de création d'un
  usager (poste, ligne, utilisateur, messagerie, compte d'authentification) est
  définitif à chaque appel ; une erreur en cours de route laisse des ressources
  créées côté Wazo, et seuls les identifiants distants permettent la reprise.
- **Inventaire transitoire** : ses lignes sont reconstruites à chaque
  chargement ; aucun historique des postes orphelins n'est conservé.
- **Tenants en lecture seule** : les fiches `wazo.tenant` sont alimentées par
  `action_sync_from_wazo` (champs `readonly`), et une seule est « configurée » à
  la fois.
- **Cloisonnement incomplet** : mesuré, le jeton d'un tenant ne l'isole pas — il
  peut lire les données d'un autre tenant en changeant l'en-tête `Wazo-Tenant`
  (voir `wazo_server/doc/P5_WAZO_SERVER_SPEC.md`).
- **Statut `Beta`** : `development_status` vaut `Beta`.

## Pistes

Aucune piste n'est consignée : le code ne porte aucun marqueur de travail en attente.
