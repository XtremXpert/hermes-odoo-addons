Miroir Odoo d'un cluster Proxmox VE : serveurs, nœuds, machines (VM et conteneurs),
pools et stockages, avec un périmètre par pools.

Chaque serveur porte son URL et son jeton API ; le champ _Pools du tenant_, séparé par
des virgules, borne ce que l'instance rapatrie — les machines et les pools hors
périmètre ne sont pas vus, et un champ vide laisse tout le serveur visible, le cas de
l'exploitant. Un jeton par serveur, pas de paramètre global : chaque serveur a sa clé.

La copie locale s'aligne sur le serveur à l'ouverture des vues de liste, au plus une
fois par minute : l'écran n'attend pas un bouton, et un serveur injoignable n'efface pas
le dernier état connu. Les actions _Démarrer_, _Éteindre_, _Redémarrer_ et _Arrêt forcé_
sont postées à l'API Proxmox puis notées dans le fil de la machine.
