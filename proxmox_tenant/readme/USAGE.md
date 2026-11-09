Pour utiliser ce module, il faut :

1. Attribuer l'un des trois groupes **Proxmox** dans l'onglet _Droits d'accès_ de la
   fiche usager : _Lecture et synchronisation_, _Utilisateur_ (qui implique le
   précédent) ou _Gestionnaire_ (qui implique les deux).
2. Créer le serveur dans _Proxmox_ > _Serveurs_ (menu réservé au groupe _Gestionnaire_)
   : nom, URL (`https://pve.exemple.com:8006`), jeton API au format
   `user@realm!tokenid=uuid`, vérification du certificat et, si besoin, la liste des
   _Pools du tenant_.
3. Ouvrir _Proxmox_ > _Objets_ > _Nœuds_, _Machines_, _Pools_ ou _Stockages_ : la copie
   locale se rafraîchit depuis le serveur si elle date de plus d'une minute, puis
   s'affiche en lecture seule.
4. Pour agir sur une machine, ouvrir sa fiche et cliquer _Démarrer_, _Éteindre_,
   _Redémarrer_ ou _Arrêt forcé_ (actions réservées au groupe _Utilisateur_). Le geste
   est écrit dans le fil et la date de dernière synchronisation de la machine est vidée,
   ce qui force sa relecture à l'ouverture suivante.

Un serveur injoignable n'empêche pas l'écran de s'ouvrir : le dernier état connu reste
affiché et l'échec part dans le journal du serveur.
