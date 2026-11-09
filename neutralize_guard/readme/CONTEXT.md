Une copie de staging ne doit rien déclencher : ni courriel, ni action planifiée.
`odoo neutralize` désactive les crons au moment du resync, mais cet état est
écrasé dès qu'un module est installé ou mis à jour : le chargement XML recrée
les `ir.cron` avec `active = True` sans passer par `toggle`, le seul endroit où
le cœur d'Odoo consulte `database.is_neutralized`. Le bouton *Exécuter
manuellement* d'une tâche planifiée lance de même la méthode sans consulter le
paramètre.

Le module déplace le garde-fou à l'exécution, en un seul point : la méthode
`_callback` de `ir.cron`, par laquelle convergent le planificateur, le bouton
manuel et les appels programmatiques. Sur une base neutralisée, elle refuse et
journalise (`_logger.info`) ; sur une base normale, elle laisse passer. Il n'y a
ni modèle propre, ni vue, ni donnée : c'est une surcharge de `_callback`, sans
état à maintenir.

Le module s'installe sur toute base destinée à être clonée en staging ; il ne
coûte rien ailleurs puisqu'il ne s'active que si le paramètre est posé. Il ne
remplace pas la neutralisation d'Odoo, il la rend durable face au chargement des
modules. Les envois de courriel directs et les appels d'API hors cron restent
hors de son périmètre : ils ne passent pas par `_callback`.
