Aucune dépendance externe : le manifeste ne déclare ni `external_dependencies`
Python ni binaire, et les bibliothèques du softphone (`sip.js`, SDK Wazo) sont
vendorisées dans `static/lib/`. Le module dépend de `wazo_tenant`, `web` et
`mail` et s'installe comme un module Odoo standard.

Le module `voip` d'Odoo Enterprise est **facultatif** : il n'est pas déclaré en
dépendance, et le pont vers ce module est un no-op s'il est absent. Pour le
softphone Enterprise, installer `voip`, puis activer le pont dans les réglages
(voir Configuration).
