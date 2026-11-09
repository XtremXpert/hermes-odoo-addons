Aucune dépendance externe : le module ne déclare ni dépendance Python ni
binaire (`external_dependencies` absent) et s'installe comme un module Odoo
standard. Le contrôleur n'utilise que la bibliothèque standard (`email`,
`hashlib`, `hmac`, `secrets`).

Le relais doit joindre `/diverse/mail-gateway/process` en HTTPS ; derrière un
mandataire qui termine TLS, Odoo doit tourner avec `--proxy-mode` (voir
Configuration). Installer le module avant de configurer le relais, pour que le
jeton puisse être créé et testé depuis Odoo.
