Aucune dépendance externe : le module ne déclare ni dépendance Python ni
binaire (`external_dependencies` absent) et s'installe comme un module Odoo
standard. Il dépend de `mailcow_tenant`, installé automatiquement ; installer
`mailcow_tenant` d'abord, `mailcow` ensuite, comme la dépendance l'impose.

`pre_init_hook` (`adopt_dashboard_xmlids`) renomme les xmlids de tableau de bord
de `mailcow_admin` vers `mailcow` : sur une installation neuve, il ne trouve rien
et ne fait rien. Les assets sont déclarés après `web/static/src/module_loader.js`
dans le manifeste ; aucun réglage manuel.
