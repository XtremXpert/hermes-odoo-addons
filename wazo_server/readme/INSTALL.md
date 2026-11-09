Aucune dépendance externe : le module réutilise le client Wazo de `wazo_tenant`
(`urllib`, `ssl`) et le client VoIP.ms de `voipms_sms`, et son manifeste ne
déclare ni `external_dependencies` Python ni binaire. Il dépend de `wazo_tenant`,
`wazo_voipms` et `web` et s'installe comme un module Odoo standard, sur l'Odoo de
l'exploitant de la plateforme uniquement.

Un tenant n'installe pas ce module : il installe `wazo_tenant` et `wazo_phone`,
et n'hérite jamais de la machinerie de création des tenants.
