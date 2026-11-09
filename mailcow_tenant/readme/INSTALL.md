Aucune dépendance externe : le client de l'API Mailcow est écrit avec `urllib`
de la bibliothèque standard, et le manifeste ne déclare ni
`external_dependencies` Python ni binaire. Le module dépend de `base` et `mail`
et s'installe comme un module Odoo standard.

Deux particularités de mise à jour, sans effet sur une installation neuve :
`pre_init_hook adopt_mailcow_admin_xmlids` reprend les xmlids de l'ancien module
`mailcow_admin`, et `migrations/20.0.2.1.0/pre-migrate.py` supprime les colonnes
de mots de passe que les versions précédentes gardaient. La variable
d'environnement `MAILCOW_API_KEY` est facultative (voir Configuration).
