Aucune dépendance externe : le client Wazo utilise `urllib` et `ssl` de la
bibliothèque standard, et le manifeste ne déclare ni `external_dependencies`
Python ni binaire. Le module dépend de `base`, `web` et `mail` et s'installe comme
un module Odoo standard.

Deux particularités de reprise, sans effet sur une installation neuve : le
`pre_init_hook adopt_wazo_phone_xmlids` et la migration
`migrations/20.0.1.0.0/pre-migration.py` adoptent les xmlids déplacés de
`wazo_phone` vers `wazo_tenant`, pour qu'une mise à jour ne perde ni vues, ni
menus, ni groupes.
