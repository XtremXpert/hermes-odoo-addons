L'écran Applications d'Odoo 20 ne montre que les modules dont le type vaut
`official` ou `industries` : le panneau de gauche n'offre aucune option « tous ».
Or un module enregistré pendant un démarrage qui met la base à jour l'est avant
le chargement de `base_import_module`, qui porte le champ `module_type` ; sa
valeur reste NULL et le module devient invisible, même à la recherche. Ce
module existe pour réparer ce défaut de plateforme, sans toucher aux modules
métier.

La correction est un `_register_hook`, donc exécuté une fois le registre
complet chargé, après chaque démarrage. Elle fait un seul UPDATE SQL sur
`ir_module_module` pour les lignes dont `module_type` est NULL, invalide le
champ puis journalise le nombre corrigé. Deux choix non évidents : la valeur
n'est écrite que si elle est NULL, donc un module `industries` n'est jamais
converti ; et l'écriture passe par SQL plutôt que par l'ORM, pour ne pas
déclencher de logique de module pendant le chargement du registre.

Le module est caché (catégorie Hidden) et ne pose ni menu ni vue : il
s'installe une fois par base et ne sert aucune fonction métier. Il est
idempotent — un démarrage sans rien à corriger ne journalise rien. La
DESCRIPTION chiffre le défaut mesuré (35 modules sur la maison, 137 en
production le 2026-10-19) ; un module `industries` reste hors du filtre
« Applications officielles », conformément au comportement d'Odoo.
