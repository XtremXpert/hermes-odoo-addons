Aucune dépendance Python ou binaire propre : le manifeste ne déclare pas
d'`external_dependencies`. Le module dépend en revanche d'`odoo_herd` — dont les
quatre dépendances Python (`kubernetes`, `pyyaml`, `boto3`, `openupgradelib`)
s'appliquent par transitivité — ainsi que de `portal`, `auth_totp`,
`auth_totp_portal` et `mail`, installés avec lui.

Le fichier `data/neutralize.sql` n'est pas chargé à l'installation : il est joué
par `odoo neutralize` sur une copie (clusters désactivés, comptes d'agents
désactivés, clés API supprimées). La migration
`migrations/20.0.1.2.0/pre-migrate.py` pose une valeur par défaut à
`ir.ui.view.visibility` pour qu'une mise à jour du module ne casse pas sur une
base où `website` n'est pas encore chargé.
