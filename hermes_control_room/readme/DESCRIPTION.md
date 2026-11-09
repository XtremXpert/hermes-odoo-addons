Rassemble sur un seul écran l'état d'exploitation de l'infrastructure : le parc Proxmox
et les clusters Kubernetes.

Les chiffres Proxmox sont lus dans les miroirs locaux entretenus par `proxmox_tenant` —
ouvrir le tableau ne contacte pas l'hyperviseur. La date de la dernière synchronisation
est affichée à côté des totaux, pour qu'un chiffre périmé ne se lise pas comme une
mesure en direct.

L'écran signale les nœuds hors ligne, la mémoire au-dessus de 90 % (alerte) ou de 97 %
(critique) et les machines arrêtées ; pour chaque cluster connu d'Odoo Herd, il montre
la joignabilité, les nœuds prêts et les déploiements en deçà du nombre de réplicas
voulu. Un cluster injoignable est annoncé comme tel : il ne masque pas les autres.
