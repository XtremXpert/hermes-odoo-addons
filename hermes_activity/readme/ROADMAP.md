L'état affiché est borné : la façade ne garde que les 50 dernières étapes
(`steps[-50:]`), et un seul message d'activité à la fois — une mise à jour d'un
`message_id` plus ancien est refusée. L'historique complet d'un traitement n'est
donc pas conservé dans le canal.

La mise à jour est un polling : le composant interroge `lire` toutes les
3 secondes et considère l'état périmé après 90 secondes sans rafraîchissement.
Il n'y a ni notification push ni bus ; un onglet fermé ne reçoit rien.

Les boutons d'approbation ne couvrent que quatre commandes (`approve`,
`approve session`, `approve always`, `deny`, avec les préfixes `/`, `!`, `.`).
Une autre invite du framework reste du texte à taper. La conversion Markdown
est volontairement petite (gras, italique, code, titres, listes, tableaux,
liens http(s)) : pas d'images, pas de listes imbriquées.

La présence repose sur un heartbeat et une tâche planifiée qui marque hors
ligne après trois minutes : un agent qui cesse de poller est annoncé hors ligne
même s'il tourne encore.
