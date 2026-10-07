Création et encadrement des **tenants** Wazo. C'est le module de **celui qui exploite le
serveur** Wazo, par opposition à `wazo_phone`, qui est le module d'**un tenant**.

- création d'un tenant (wazo-auth), avec son **contexte interne** et ses **plages
  d'extensions** (postes, groupes d'appel) ;
- fabrication de l'**utilisateur administrateur** du tenant et de son **jeton d'API** —
  jamais saisi à la main ;
- remise des coordonnées au tenant (URL, tenant, jeton, contexte) ;
- renouvellement du jeton d'un tenant, sans détruire le tenant ni ses postes ;
- adoption des tenants d'un Wazo déjà peuplé ;
- suppression gardée : refusée tant que le tenant porte des postes ou des lignes.

Dépend de `wazo_phone` (client et réglages partagés) ; un tenant installe `wazo_phone`
seul et n'hérite jamais de cette machinerie.
