Le champ `allowed_ips` existe mais n'est pas appliqué : son aide le dit
(« Enforced in V2; field present for forward compatibility »). Aucun compteur,
aucune limitation de débit : un jeton valide peut appeler `process` autant de
fois que le relais le fait.

Le jeton n'est montré qu'une fois, à sa création : seule l'empreinte est
stockée, donc un jeton perdu ne se retrouve pas — il faut le révoquer et en
générer un autre. `Revoke` désactive sans supprimer, ce qui conserve la trace
d'usage mais laisse la ligne en base.

Le module ne traite que l'entrant : aucun envoi, aucune gestion de file
d'attente. Le HTTPS est refusé par défaut ; derrière un mandataire qui termine
TLS, Odoo doit tourner avec `--proxy-mode`. `GET /health` répond sans
authentification et expose la version du module et d'Odoo : c'est une sonde de
vie assumée, pas une route à exposer largement.
