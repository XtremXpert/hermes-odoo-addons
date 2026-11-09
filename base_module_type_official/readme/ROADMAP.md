La correction ne traite que les types NULL : un module dont `module_type`
vaudrait une autre valeur n'est pas réparé, et un module `industries` n'est
volontairement jamais converti. Il n'existe ni réglage ni désactivation : le
seul moyen d'arrêter la correction est de désinstaller le module.

L'écriture est un UPDATE SQL direct, hors ORM. Elle ne laisse donc aucune trace
dans l'historique des enregistrements, seulement la ligne de journal
« module_type « official » donné à N module(s) » quand il y avait quelque chose
à corriger.

Le module est un contournement assumé : si une version ultérieure d'Odoo
remplit correctement `module_type` à l'enregistrement, ce module devient
inutile et peut être désinstallé.
