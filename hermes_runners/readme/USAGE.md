Ouvrir **Runners** dans le menu principal.

Chaque ligne donne le pool, la phase, l'identifiant GitHub et l'ancienneté du
pod.

Cette ancienneté demande une lecture prudente : un pool configuré avec
`minRunners > 0` garde un pod pré-provisionné en attente, qui peut afficher
plusieurs jours d'âge sans qu'aucun job n'y soit bloqué. L'âge ne renseigne sur
un job qu'une fois la phase connue — et le module ne lit pas encore le job
lui-même. C'est pourquoi il est présenté comme une ancienneté, sans seuil
d'alerte.

Le rafraîchissement est manuel (bouton) ou automatique toutes les 30 secondes.
L'heure du dernier instantané est affichée : une donnée périmée présentée comme
live est pire que pas de donnée.
