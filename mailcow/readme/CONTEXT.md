Administrer Mailcow depuis Odoo est une chose — les fiches, les écritures, les
réglages de connexion : c'est `mailcow_tenant` — en donner une vue d'ensemble
lisible en est une autre. Ce module porte seulement la couche de présentation :
deux tableaux de bord OWL, l'ensemble du serveur et un par domaine, et les
alertes qui en découlent. Le séparer évite de mêler une interface à un modèle de
données réutilisable par les agents.

Les chiffres viennent des objets de `mailcow_tenant`, donc de la copie locale.
Le rafraîchissement automatique (30 secondes) ne relit que l'état d'Odoo et
n'interroge jamais Mailcow ; tirer du serveur reste un geste explicite, par
« Synchroniser depuis Mailcow » ou « Synchroniser ce domaine ». Ce choix évite
de mettre la charge d'un tableau de bord ouvert sur le serveur de messagerie.
Les alertes viennent des données du module voisin et sont triées à l'affichage
par gravité ; un clic ouvre la liste filtrée correspondante.

Deux contraintes d'installation sont assumées dans le manifeste : les assets
doivent être chargés après `web/static/src/module_loader.js` — sinon le client
web meurt au chargement, sans erreur côté serveur — et un `pre_init_hook` adopte
les xmlids du tableau de bord renommés `mailcow_admin` → `mailcow`. La clé API
reste celle de `mailcow_tenant` ; elle peut venir de l'environnement, et elle est
ignorée sur une base neutralisée.
