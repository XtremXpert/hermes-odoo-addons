## Limites connues

- **Journal non temps réel** : il se met à jour à la synchronisation, manuelle
  ou planifiée ; `doc/UTILISATEUR.md` le dit explicitement.
- **Lecture seule sur les postes** : l'utilisateur ne modifie ni les postes ni la
  configuration (`doc/UTILISATEUR.md`, « Rappels et limites »).
- **Pont softphone Enterprise optionnel** : le module `voip` d'Enterprise n'est
  pas une dépendance. Sans lui, le pont est un no-op ; la section de réglages
  n'apparaît que si `voip` est installé et que le serveur Wazo expose `wss`.
- **Bibliothèques vendorisées** : `static/lib/sip.js` et
  `static/lib/wazo-sdk.js` sont des fichiers tiers maintenus hors du dépôt ; le
  SDK est servi dans son propre paquet (`wazo_phone.assets_sdk`) et chargé à la
  demande.
- **Ordre des actifs imposé** : les fichiers doivent rester après
  `web/static/src/module_loader.js` ; modifier la déclaration des actifs peut
  blanchir le client web sans erreur serveur (commentaire du manifeste).
- **Ancienne table conservée** : la migration `20.0.3.0.0` laisse en place
  `wazo_ring_group_wazo_user_rel` comme donnée de retour arrière ; elle est
  inerte, plus aucun modèle ne la déclare.
- **Couverture JavaScript à part** : les tests du softphone sont des tests Node
  (`static/tests/`), qu'aucun test Python ne voit, et rien ne charge le client
  web dans un navigateur (voir la note du `README.md` du dépôt).
- **Statut `Beta`** : `development_status` vaut `Beta`.

## Pistes

Aucune piste n'est consignée : le code ne porte aucun marqueur de travail en attente.
