La connexion se règle dans _Mailcow_ > _Configuration_, réservé aux administrateurs, et
se retrouve aussi sous _Réglages_ > _Mailcow_ :

- **URL du serveur Mailcow** : URL de base, sans `/api/v1` ;
- **Clé API Mailcow** : clé créée dans l'interface d'administration de Mailcow, section
  API ;
- **Tester la connexion** : lit la version du serveur et le nombre de domaines qu'il
  renvoie ; un serveur qui ne renvoie aucun domaine est annoncé comme une alerte, pas
  comme un succès.

La variable d'environnement `MAILCOW_API_KEY` du conteneur Odoo l'emporte sur le
réglage, qui est alors masqué ; elle est ignorée sur une base neutralisée, de sorte
qu'un staging cloné n'agit jamais sur le vrai serveur. À défaut, la clé saisie est
rangée dans le paramètre système `mailcow.api_key`.

Le périmètre du tenant se règle par le paramètre système `mailcow.allowed_domains`, une
liste de domaines séparés par des virgules : une instance de tenant ne rapatrie que ces
domaines ; vide, tout le serveur est visible.

Trois groupes sont déclarés dans la catégorie **Mailcow** de la fiche usager : _Lecture
et synchronisation_ (lire et aligner, sans écrire sur Mailcow ni voir de mot de passe —
le groupe des agents), _Utilisateur_ (créer, mettre à jour et ouvrir le menu) et
_Gestionnaire_ (cumule les deux, ajoute les suppressions et les mots de passe).
