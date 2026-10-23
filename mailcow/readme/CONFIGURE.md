Dans Réglages → **Mailcow**, renseigner l'URL du serveur, puis tester la connexion.

Clé API, de préférence hors de la base : la variable d'environnement `MAILCOW_API_KEY`
du conteneur Odoo, alimentée par un Secret Kubernetes copié depuis Vaultwarden. Elle
l'emporte sur le réglage, qui est alors masqué. Elle est ignorée sur une base neutralisée
(`database.is_neutralized`) : un staging cloné n'agit jamais sur le vrai serveur.

À défaut, la clé saisie dans les réglages est stockée dans `ir.config_parameter`
(`mailcow.api_key`), donc dans les sauvegardes et les clones de la base.
