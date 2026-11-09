La CI tourne sur des runners GitHub Actions auto-hébergés (ARC) dans Kubernetes.
Quand un job reste en attente, rien ne le dit : il n'a pas encore de pod. Ce
module répond à la seule question utile — est-ce que la file avance ou est-ce
que tout est pris ? — en lisant les runners qui existent dans le cluster. Il est
séparé de `odoo_herd`, qui gère les clusters, pour rester un simple tableau de
bord.

Le serveur lit deux ressources personnalisées d'ARC (`AutoscalingRunnerSet` pour
les pools, `EphemeralRunner` pour les pods) via le client Kubernetes que
`odoo_herd` sait construire depuis ses kubeconfigs. L'ancienneté d'un runner est
l'information clé : ARC ne garde un pod que le temps d'un job, donc un pod de
plusieurs heures signale un job bloqué. L'occupation d'un pool est calculée sur
`maxRunners`, pas sur le nombre de pods : 2/2 est saturé, 0/1 est libre, 0/0
signifie un pool en pause. L'agrégation est une fonction pure, testable sans
cluster.

Une erreur sur un cluster est rapportée dans son entrée, jamais levée : un
cluster muet ne masque pas les autres. Le module ne se connecte ni à GitHub ni
directement au cluster côté navigateur : le serveur compose l'instantané,
l'interface l'affiche avec l'heure de l'instantané et un rafraîchissement de
30 secondes. La moitié « file d'attente GitHub » n'est pas lue ici (voir
Roadmap).
