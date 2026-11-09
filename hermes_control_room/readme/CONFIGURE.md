Aucun réglage propre, vérifié dans le module : il n'expose ni
`res.config.settings`, ni paramètre système, ni groupe, et son manifeste ne
charge que `views/menus.xml`.

Le menu _Salle de contrôle_ est réservé au groupe
`proxmox_tenant.group_proxmox_manager` (groupe du module voisin, pas du module).
La configuration réelle se fait dans les modules qui portent la donnée : URL et
jeton des serveurs dans `proxmox_tenant`, clusters et kubeconfigs dans
`odoo_herd`. Sans au moins un serveur synchronisé ou un cluster déclaré, le
tableau n'a rien à montrer.
