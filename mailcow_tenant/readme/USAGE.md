Pour utiliser ce module, il faut :

1. Renseigner l'URL et la clé API dans _Mailcow_ > _Configuration_ (ou _Réglages_ >
   _Mailcow_), puis cliquer _Tester la connexion_.
2. Attribuer les groupes **Mailcow** dans l'onglet _Droits d'accès_ de la fiche usager :
   _Utilisateur_ (ou _Gestionnaire_) pour ouvrir le menu Mailcow ; _Lecture et
   synchronisation_ pour un agent qui lit et synchronise par l'API sans passer par
   l'écran.
3. Amener l'état du serveur dans Odoo avec _Mailcow_ > _Tout synchroniser_, ou
   _Synchroniser depuis Mailcow_ dans l'en-tête d'une liste ; _Aperçu de la
   synchronisation_ décrit les changements sans rien écrire.
4. Créer les fiches dans _Mailcow_ > _Objets_ > _Domaines_, _Boîtes mail_, _Alias_ ou
   _Adresses courriel_, puis les pousser avec _Créer sur Mailcow_ (ou _Pousser la
   sélection vers Mailcow_ depuis la liste). Une fiche déjà synchronisée se met à jour
   avec _Mettre à jour sur Mailcow_.
5. Sur une boîte, _Changer le mot de passe_ et _Mot de passe applicatif_ affichent le
   secret une seule fois ; _En faire le fourre-tout_ crée ou réoriente l'alias
   `@domaine`.
6. Les fiches retirées du serveur apparaissent sous _Mailcow_ > _Disparues du serveur_,
   par objet ; on peut les archiver avec _Oublier les fiches sélectionnées_ ou les
   supprimer localement, sans toucher au serveur.

Sur la fiche d'un usager, le bouton _Créer la boîte Mailcow_ crée la fiche de boîte
correspondant à son adresse courriel, à pousser ensuite vers Mailcow, si son domaine est
déjà synchronisé (groupe _Gestionnaire_).

Les suppressions sur le serveur et les changements de mot de passe sont réservés au
groupe _Gestionnaire_ ; les réglages, aux administrateurs. _Utilisateur_ crée et met à
jour ; _Lecture et synchronisation_ n'écrit jamais sur Mailcow.
