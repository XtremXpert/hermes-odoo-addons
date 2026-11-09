Aucune dépendance externe : le module ne déclare ni dépendance Python ni
binaire (`external_dependencies` absent) et s'installe comme un module Odoo
standard. Il dépend de `mail`.

L'installation crée le compte `hermes_n3` ; elle ne crée ni mot de passe ni clé
API. La clé est créée ensuite par un humain (voir Configuration). Sur une copie
neutralisée, `data/neutralize.sql` est exécuté par `odoo neutralize` ; rien à
faire après une resynchronisation.
