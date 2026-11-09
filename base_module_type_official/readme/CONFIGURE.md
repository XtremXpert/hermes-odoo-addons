Aucun réglage propre, vérifié dans le module : il n'expose ni
`res.config.settings`, ni paramètre système, ni groupe de sécurité, et son
manifeste ne charge aucun fichier `data`. Il n'y a donc rien à configurer : la
correction s'applique seule à chaque chargement du registre, et le seul effet
visible est la ligne de journal annonçant le nombre de modules corrigés.
