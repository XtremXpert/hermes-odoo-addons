Aucune dépendance externe : le manifeste ne déclare ni `external_dependencies`
Python ni binaire, et le client Proxmox est celui, en `urllib`, de
`proxmox_tenant`. Le module dépend de `proxmox_tenant` et `mail` et s'installe
comme un module Odoo standard, après `proxmox_tenant` (Odoo respecte l'ordre des
dépendances). Il s'installe sur l'Odoo de la plateforme, pas sur celui d'un
tenant.
