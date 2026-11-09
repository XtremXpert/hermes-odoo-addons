La moitié « file d'attente GitHub » n'est pas implémentée. Le docstring du modèle
annonce un `github_queue_snapshot` qui échouerait proprement quand le jeton
manque, mais aucune méthode de ce nom n'existe dans `models/runners.py` :
l'instantané ne lit que le cluster. Un job en file n'a pas de pod, donc il
n'apparaît nulle part ; le gabarit le dit à l'utilisateur (« Aucun runner actif.
Un job en file n'a pas encore de pod… »).

L'occupation d'un pool est un rapport à `maxRunners`, pas une mesure de la file
GitHub : un pool libre ne prouve pas que la file est vide. L'ancienneté d'un
runner est calculée au moment de l'instantané ; elle n'est pas rafraîchie entre
deux appels.

Les clusters actifs sont lus séquentiellement et sans délai d'attente paramétré :
un cluster lent allonge l'appel pour les autres. Une erreur est rapportée dans
l'entrée du cluster concerné, jamais levée, et il n'y a pas d'alerte globale. Le
rafraîchissement de l'écran est de 30 secondes.
