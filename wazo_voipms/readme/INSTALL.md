Aucune dépendance externe : le module réutilise le client Wazo de `wazo_tenant`
et le client VoIP.ms de `voipms_sms`, tous deux en `urllib`, et son manifeste ne
déclare ni `external_dependencies` Python ni binaire. Il dépend de `wazo_tenant`
et `voipms_sms` et s'installe comme un module Odoo standard.

Les deux modules dépendants doivent être configurés (URL et jeton Wazo,
utilisateur et jeton VoIP.ms) et le serveur Wazo joignable en SIP par VoIP.ms
pour le routage entrant ; ce sont des prérequis d'usage, pas d'installation.
