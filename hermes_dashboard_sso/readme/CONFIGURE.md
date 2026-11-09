Aucun réglage propre, vérifié dans le module : il n'expose ni
`res.config.settings`, ni paramètre système, et ne déclare aucun groupe.

Le seul droit à régler est le groupe standard _Administration / Paramètres_
(`base.group_system`) : seuls ses membres peuvent ouvrir `/hermes/sso/authorize`,
et sa revérification a lieu au moment de l'échange du code. Le module écrit une
ligne d'ACL (`security/ir.model.access.csv`) pour que la table des codes soit
lisible et inscriptible par ce groupe, conformément à la convention OCA ; sinon
rien à configurer.
