Création et encadrement des **tenants** Wazo. C'est le module de **celui qui entretient
le serveur** Wazo (l'exploitant de la plateforme), par opposition à `wazo_tenant`
(exploitation d'un tenant) et `wazo_phone` (usagers du téléphone).

- création d'un tenant (wazo-auth), avec son **contexte interne** et ses **plages
  d'extensions** (postes, groupes d'appel) ;
- fabrication de l'**utilisateur administrateur** du tenant et de son **jeton d'API** —
  jamais saisi à la main ;
- remise des coordonnées au tenant (URL, tenant, jeton, contexte) ;
- renouvellement du jeton d'un tenant, sans détruire le tenant ni ses postes ;
- adoption des tenants d'un Wazo déjà peuplé ;
- suppression gardée : refusée tant que le tenant porte des postes ou des lignes ;
- **tableau de bord de l'exploitant** (menu « Serveur Wazo → Tableau de bord ») :
  état des tenants et expiration de leurs jetons (alerte à 30 jours), trunk SIP du
  pont VoIP.ms (`wazo_voipms`) avec vérification de l'enregistrement, DIDs routés
  ou muets, solde du compte VoIP.ms — relu **sur demande seulement**, un
  chargement de page n'appelle jamais le fournisseur.

Dépend de `wazo_tenant` (modèles d'exploitation) et de `wazo_voipms` (état du
pont) ; un tenant installe `wazo_tenant` + `wazo_phone` et n'hérite jamais de
cette machinerie.
**Limite connue, mesurée** : le jeton d'un tenant **ne le cloisonne pas**. Un jeton de
tenant peut lire les données d'un autre tenant en changeant l'en-tête `Wazo-Tenant`. La
frontière réelle se place à l'**URL** — un point d'entrée par tenant qui impose
l'en-tête —, pas dans le jeton. Voir `doc/P5_WAZO_SERVER_SPEC.md`.
