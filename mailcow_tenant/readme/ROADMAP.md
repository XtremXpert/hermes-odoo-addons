## Limites connues

- **Clé API en clair quand l'environnement ne la fournit pas** : hors
  `MAILCOW_API_KEY`, la clé est rangée dans le paramètre système
  `mailcow.api_key`, donc dans la base, ses sauvegardes et ses clones. La
  variable d'environnement est la voie recommandée.
- **Rafraîchissement borné à une minute** : `RAFRAICHISSEMENT_MIN_S = 60` ; une
  liste rouverte dans la minute garde la copie précédente, et il n'existe pas de
  webhook Mailcow pour forcer la relecture.
- **Disparition non destructive** : une fiche absente du serveur passe à
  `synced = False` et reste en base ; le nettoyage est manuel (*Oublier les
  fiches sélectionnées* ou purge locale), jamais automatique.
- **Listage vide refusé** : `refuser_la_disparition_totale` traite un serveur
  qui ne renvoie plus aucune entrée comme une panne probable. Après une
  suppression volontaire de tous les domaines côté Mailcow, la synchronisation
  refuse de conclure : il faut oublier ou purger les fiches localement.
- **Résultat incertain sur timeout** : le client distingue une erreur franche
  d'un délai dépassé (`RESULTAT_INCERTAIN`) ; dans le second cas, la
  modification a pu être appliquée sur Mailcow et il faut synchroniser avant de
  réessayer.
- **Mots de passe non récupérables** : ils ne sont jamais stockés (choix de
  conception) ; un mot de passe perdu se régénère, il ne se relit pas.
- **Mise à jour d'une base ancienne** : le `pre_init_hook`
  `adopt_mailcow_admin_xmlids` et le script `migrations/20.0.2.1.0/pre-migrate.py`
  sont nécessaires pour reprendre les xmlids de `mailcow_admin` et effacer les
  colonnes de mots de passe ; une base encore sur l'ancien module en dépend.

## Pistes

Aucune piste n'est consignée : le code ne porte aucun marqueur de travail en attente.
