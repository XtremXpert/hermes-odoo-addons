Pour utiliser ce module, il faut :

1. Avoir installé et configuré `mailcow_tenant` (URL et clé API du serveur) : ce module
   s'appuie sur ses objets et ses réglages.
2. Attribuer un groupe Mailcow à l'usager — _Utilisateur_ ou _Gestionnaire_ — pour
   qu'il ouvre le menu _Mailcow_.
3. Ouvrir _Mailcow_ > _Vue d'ensemble_ : les alertes à traiter (plafonds, comptes
   dormants, alias cassés) s'affichent en cartes ; un clic ouvre la liste filtrée
   correspondante.
4. Choisir l'onglet _Domaines_, _Boîtes_ ou _Alias_ pour le détail, chercher et trier
   les colonnes ; un clic sur un domaine ouvre son tableau de bord, un clic sur une
   boîte ou un alias ouvre sa fiche.
5. Cliquer **Synchroniser depuis Mailcow** pour relire le serveur, ou **Rafraîchir
   maintenant** pour ne relire que l'état local ; la bascule _Rafraîchir tout seul,
   toutes les 30 secondes_ entretient l'affichage sans interroger Mailcow.

Sur le tableau d'un domaine, **Nouvelle boîte** et **Nouvel alias** créent les fiches
correspondantes ; **Synchroniser ce domaine** n'aligne que ce domaine ; **Tous les
domaines** revient à la vue d'ensemble. Les créations, mises à jour et suppressions
sur le serveur restent celles de `mailcow_tenant`.
