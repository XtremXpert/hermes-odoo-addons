Couche **tenant** de la téléphonie Wazo, exploitée par l'opérateur d'un
client (xtremxpert.ca, diverse-cite.com, …).

Contient :

* le client REST `WazoClient` (confd, authd, call-logd) et les réglages de
  connexion (URL, jeton API, tenant, contexte des lignes) ;
* `wazo.user`, `wazo.ring.group` — utilisateurs et groupes d'appel du
  tenant, avec synchronisation vers le PBX ;
* `wazo.cdr` — le journal d'appels synchronisé (cron) ;
* `wazo.extension.mixin` + assistant d'inventaire des postes du contexte ;
* les groupes « Téléphonie Wazo : Utilisateur / Gestionnaire ».
