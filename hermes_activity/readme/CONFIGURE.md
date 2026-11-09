Aucun réglage propre, vérifié dans le module : il n'expose ni
`res.config.settings`, ni paramètre système, et ne déclare aucun groupe — son
manifeste ne charge que `data/presence_cron.xml`. Rien à configurer.

Les droits d'accès sont ceux des modules voisins : les façades reconnaissent les
groupes `group_agent` de `hermes_n1_audit`, `hermes_n2_support` et
`hermes_n3_infra` quand ces modules sont installés, et `hermes_n1_audit` reste
la dépendance obligatoire. La tâche planifiée « Hermes : expiration de la
présence » est créée à l'installation et tourne toutes les minutes.
