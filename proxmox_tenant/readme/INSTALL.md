Aucune dépendance externe : le client Proxmox utilise `urllib` et `ssl` de la
bibliothèque standard, et le champ `BigInteger` (`fields_bigint.py`) est défini
dans le module — le manifeste ne déclare ni `external_dependencies` Python ni
binaire. Le module dépend de `base` et `mail` et s'installe comme un module Odoo
standard. Il doit pouvoir joindre l'API du cluster (`https://…:8006`) en HTTPS
sortant, et la vérification du certificat se désactive par serveur si besoin.
