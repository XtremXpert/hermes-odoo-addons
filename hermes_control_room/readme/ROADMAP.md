Les chiffres Proxmox viennent des miroirs de `proxmox_tenant` : entre deux
synchronisations, ils peuvent être périmés. Le bandeau affiche la date de la
dernière synchronisation, ou « Aucune synchronisation enregistrée », mais rien
ne force une relecture avant l'affichage.

Les clusters sont lus séquentiellement dans `kubernetes_snapshot`, sans délai
d'attente paramétré par cluster : un cluster lent allonge l'appel pour tous les
autres. Une erreur est bien capturée par cluster (elle n'est pas levée), mais
elle n'empêche pas cet allongement.

Les seuils d'alerte mémoire (90 % avertissement, 97 % critique) sont des
constantes du module, non réglables. Les alertes sont recalculées à chaque
lecture : elles ne sont ni stockées, ni notifiées, ni historisées.
