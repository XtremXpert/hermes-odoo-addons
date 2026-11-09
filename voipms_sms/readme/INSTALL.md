Aucune dépendance externe : le client de l'API VoIP.ms est écrit avec `urllib` de
la bibliothèque standard, et le manifeste ne déclare ni `external_dependencies`
Python ni binaire. Le module dépend de `base` et s'installe comme un module Odoo
standard. L'instance doit pouvoir joindre `https://voip.ms/api/v1/rest.php` en
HTTPS sortant ; les identifiants se renseignent après installation, dans
*Réglages* > *SMS VoIP.ms*.
