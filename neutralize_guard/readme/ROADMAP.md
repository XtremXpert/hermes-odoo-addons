## Limites connues

- **Périmètre limité aux tâches planifiées** : le garde-fou ne couvre que
  `ir.cron._callback`. Un envoi de courriel ou un appel d'API déclenché hors
  d'un cron — par exemple depuis un bouton ou une action serveur — n'est pas
  filtré.
- **Aucune trace consultable depuis Odoo** : le refus part au journal serveur
  (`_logger.info`), sans enregistrement en base. Sur une base neutralisée, il
  faut lire les logs pour constater qu'une tâche a été bloquée.
- **Aucun modèle, aucune vue, aucune donnée** : le module ne se configure pas et
  n'affiche rien ; son seul indicateur est le paramètre
  `database.is_neutralized`, posé par le cœur d'Odoo.
- **Statut `Beta`** : `development_status` vaut `Beta`.

## Pistes

Aucune piste n'est consignée : le code ne porte aucun marqueur de travail en attente.
