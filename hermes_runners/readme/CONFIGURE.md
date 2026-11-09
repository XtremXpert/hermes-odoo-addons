Aucun réglage propre, vérifié dans le module : il n'expose ni
`res.config.settings`, ni paramètre système, ni groupe, et son manifeste ne
charge que `views/menus.xml`.

Le menu _Runners_ est réservé au groupe standard `base.group_system` ; aucun
groupe n'est déclaré par le module. La configuration réelle se fait dans
`odoo_herd` : les clusters et leurs kubeconfigs sont lus dans `k8s.cluster`, et
le module ne garde aucun jeton GitHub puisqu'il n'interroge pas GitHub.
