Aucune dépendance externe : le manifeste ne déclare ni `external_dependencies`
Python ni binaire, et le module n'a aucun fichier de données à charger. Il
s'installe comme un module Odoo standard ; sa seule dépendance est `base`, qu'il
surcharge (`ir.cron._callback`). Rien à faire après l'installation : le
garde-fou s'active de lui-même sur une base neutralisée.
