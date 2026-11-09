Ce module ne fait que présenter : les créations, mises à jour et suppressions sur
le serveur restent celles de `mailcow_tenant`, dont il dépend. Il ne peut donc
pas être installé seul.

Le rafraîchissement automatique de 30 secondes relit l'état local d'Odoo et
n'interroge pas Mailcow ; les chiffres peuvent donc être périmés entre deux
synchronisations explicites. L'écriture incertaine (délai de 30 secondes)
documentée dans la DESCRIPTION concerne les écritures de `mailcow_tenant`, pas ce
tableau de bord.

La clé API vient de la variable d'environnement `MAILCOW_API_KEY` ou, à défaut,
de `ir.config_parameter` (`mailcow.api_key`) — donc des sauvegardes et des clones
de la base. Elle est ignorée sur une base neutralisée, mais le module lui-même
n'a pas de réglage propre.

Deux contraintes de maintenance sont inscrites au manifeste : les assets doivent
être chargés après `web/static/src/module_loader.js`, sinon le client web meurt
au chargement sans erreur serveur ; et `pre_init_hook` n'adopte que les xmlids
dont le nom contient `tableau` — les autres sont adoptés par `mailcow_tenant`.
