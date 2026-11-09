Pour utiliser ce module, il faut :

1. Attribuer le groupe **Téléphonie Wazo : Gestionnaire** aux exploitants : le menu
   _Serveur Wazo_ est réservé à ce groupe.
2. Ouvrir _Serveur Wazo_ > _Tenants_ et créer un tenant : nom, `slug`, tenant parent,
   puis le contexte et les plages d'extensions (postes, groupes, files, conférences).
   Les plages laissées par défaut reçoivent le prochain bloc de mille libre.
3. Sur la fiche, cliquer **Créer sur Wazo** : le tenant, son contexte, ses plages, son
   administrateur et son jeton sont fabriqués sur le PBX. La section _Coordonnées à
   remettre au tenant_ donne le bloc à transmettre.
4. **Renouveler le jeton** fabrique un jeton neuf et révoque l'ancien (l'Odoo du client
   doit recevoir la nouvelle fiche) ; **Supprimer le tenant** est refusé tant que le
   tenant porte des postes ou des lignes.
5. Sur un Wazo déjà peuplé, cliquer **Adopter les tenants du PBX** dans l'en-tête de la
   liste pour créer les fiches correspondantes.
6. Ouvrir _Serveur Wazo_ > _Tableau de bord_ : tenants et expiration de leurs jetons
   (alerte à 30 jours), trunk du pont VoIP.ms et enregistrement, DIDs routés ou muets,
   solde VoIP.ms. **Rafraîchir** relit l'état local ; **Actualiser le solde** et
   **Vérifier l'enregistrement** du trunk interrogent le fournisseur à la demande.
7. _Serveur Wazo_ > _DIDs (tous)_ liste tous les DIDs du compte VoIP.ms avec leur
   tenant, leur état de routage et leur destination.
