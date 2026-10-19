Rend visibles dans l'écran **Applications** les modules qui n'y apparaissent jamais, quelle que soit la recherche.

- Le panneau de gauche de l'écran Applications filtre toujours sur un type de module : « Applications officielles » (`official`, par défaut) ou « Secteurs d'activité » (`industries`). Il n'a pas d'option « tous ».
- Un module enregistré pendant un démarrage qui met la base à jour (`-i`, `-u`, nouveau paquet Odoo) l'est avant le chargement de `base_import_module`, qui porte le champ `module_type`. Son type reste vide, et le module n'entre dans aucun des deux filtres. Constaté le 2026-10-19 : 35 modules sur maison (dont `mailcow_admin`), 137 sur la production de diverse-cite.
- À chaque chargement du registre, le module donne le type `official` aux modules dont le type est vide. Les modules `industries` ne sont pas touchés.
