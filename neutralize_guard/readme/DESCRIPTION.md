Une copie de staging ne doit rien déclencher : ni courriel, ni action planifiée.

`odoo neutralize` désactive les crons au moment du resync, mais cet état est
écrasé dès qu'un module est installé ou mis à jour — le chargement XML recrée
les `ir.cron` avec `active = True`, sans passer par `toggle`, le seul endroit
où le cœur d'Odoo consulte `database.is_neutralized`.

Résultat : sur un staging, les crons se remettent à tourner après chaque
déploiement, et le bouton « Exécuter manuellement » les lance même sans
planificateur.

Ce module déplace le garde-fou à l'exécution : sur une base neutralisée,
`_callback` refuse et journalise. Les trois voies sont couvertes — le
planificateur, le déclenchement manuel et les appels programmatiques — parce
qu'elles convergent toutes vers cette méthode.
