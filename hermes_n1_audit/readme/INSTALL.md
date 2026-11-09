Aucune dépendance externe : le module ne déclare ni dépendance Python ni
binaire (`external_dependencies` absent) et s'installe comme un module Odoo
standard. Il dépend de `mail`.

Ordre de livraison : installer ce module avant de déployer les nouveaux outils
N1 et le SOUL N1, comme le précise la DESCRIPTION — les appels historiques
`modifier`/`capabilities` gardent leur comportement. `data/neutralize.sql` est
exécuté par `odoo neutralize`, pas à l'installation ; rien à faire après une
resynchronisation. Les tests demandent un PostgreSQL éphémère
(`tools/test-hermes-audit.sh IMAGE`).
