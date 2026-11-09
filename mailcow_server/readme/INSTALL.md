Aucune dépendance externe : le manifeste ne déclare ni `external_dependencies`
Python ni binaire, et le module n'a aucun fichier de données à charger. Il
s'installe comme un module Odoo standard, après `mailcow_tenant` qu'il déclare
en dépendance (Odoo installe celui-ci d'abord). Une seule instance le porte :
l'Odoo de l'exploitant de la plateforme, pas celui d'un tenant.
