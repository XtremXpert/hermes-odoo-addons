Trois groupes sont déclarés ; ils s'emboîtent et s'attribuent dans l'onglet _Droits
d'accès_ de la fiche usager :

- **Proxmox — Lecture et synchronisation** : voir les fiches et aligner la copie locale
  sur le serveur ;
- **Proxmox — Utilisateur** : en plus, démarrer, éteindre, redémarrer ou forcer l'arrêt
  d'une machine ;
- **Proxmox — Gestionnaire** : en plus, créer, modifier et supprimer les fiches, dont
  les serveurs.

La connexion se règle sur chaque fiche serveur, dans _Proxmox_ > _Serveurs_ : URL, jeton
API (champ réservé au groupe _Gestionnaire_), vérification du certificat et _Pools du
tenant_. Le rafraîchissement automatique à l'ouverture des listes est limité à un
passage par minute et par objet ; aucun réglage global n'est à renseigner.
