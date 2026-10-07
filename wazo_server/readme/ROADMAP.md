**Limite connue, mesurée** : le jeton d'un tenant **ne le cloisonne pas**. Un jeton de
tenant peut lire les données d'un autre tenant en changeant l'en-tête `Wazo-Tenant`. La
frontière réelle se place à l'**URL** — un point d'entrée par tenant qui impose
l'en-tête —, pas dans le jeton. Voir `doc/P5_WAZO_SERVER_SPEC.md`.
