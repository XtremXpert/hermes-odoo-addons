État des runners GitHub Actions auto-hébergés (ARC) qui exécutent la CI.

Le tableau de bord lit le cluster : chaque job attribué y crée un
`EphemeralRunner`, avec sa phase, son identifiant GitHub et son ancienneté. Il
montre aussi les pools (`AutoscalingRunnerSet`) et leur taux d'occupation, parce
que la vraie question est « est-ce que la file avance ou est-ce que tout est
pris ? ».

La distinction qui compte : le cluster sait quels runners **existent**, pas ce
qui **attend**. Un job en file n'a pas encore de pod — il n'est visible que par
l'API GitHub. Cette moitié n'est pas encore implémentée ; le module le dit
plutôt que de laisser croire que « zéro runner » signifie « rien à faire ».
