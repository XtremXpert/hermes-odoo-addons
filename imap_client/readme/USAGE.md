Pour utiliser ce module, il faut :

1. Attribuer les groupes **IMAP — Gestionnaire** ou **IMAP — Lecture** aux usagers
   concernés, dans l'onglet _Droits d'accès_ de la fiche usager.
2. Créer le compte dans _Courriels_ > _Comptes_ (menu réservé au groupe gestionnaire) :
   nom, propriétaire, serveur IMAP, port (993 par défaut), SSL, utilisateur et mot de
   passe.
3. Vérifier la connexion avec _Tester_ sur la fiche du compte, puis lancer
   _Synchroniser_ : les dossiers sont créés, puis les en-têtes des derniers messages de
   chaque dossier sont rapatriés.
4. Consulter _Courriels_ > _Boîte_ pour les messages rapatriés, avec le contact reconnu,
   et _Courriels_ > _Dossiers_ pour les dossiers découverts et leur nombre de non-lus.

Sur un message, _Lire_ télécharge le corps puis le marque lu sur le serveur ; _Marquer
lu_ pose le drapeau sur le serveur sans télécharger le corps ; _Répondre_ ouvre un
assistant pré-rempli dont l'envoi passe par le serveur sortant configuré dans Odoo.

La synchronisation est réservée au groupe **IMAP — Gestionnaire**. Un usager non
gestionnaire ne voit que les comptes dont il est propriétaire ; le gestionnaire voit
tous les comptes.
