Aucun réglage propre : le module n'expose ni `res.config.settings`, ni paramètre
système, ni groupe de sécurité — il n'a ni modèle, ni vue, ni fichier de données
et son `__init__.py` est vide. Il ne se configure donc pas ; la connexion au
serveur Mailcow reste celle posée par `mailcow_tenant` dans *Réglages* >
*Mailcow* (URL et clé API), et les droits restent les trois groupes Mailcow de
ce module.
