## Limite connue, mesurée

**Le jeton d'un tenant ne cloisonne pas.** Un jeton de tenant peut lire les
données d'un autre tenant en changeant l'en-tête `Wazo-Tenant` : les ACL de Wazo
sont des chaînes indépendantes du tenant. La frontière réelle se place à
l'**URL** — un point d'entrée par tenant qui impose l'en-tête —, pas dans le
jeton. Voir `doc/P5_WAZO_SERVER_SPEC.md`.

## Autres limites

- **Secrets non relus** : wazo-auth ne rend ni le jeton ni le mot de passe
  d'administration après création. `admin_password` et `api_token` sont des
  champs `Char`, réservés au groupe gestionnaire mais stockés en clair en base ;
  la fiche de remise les donne à ressaisir, et *Renouveler le jeton* les
  régénère.
- **Listage cloisonné** : un parent n'est pas lisible avec l'en-tête de son
  enfant (`GET /tenants/<uuid>` répond 404 « unknown-tenant ») ; l'adoption
  interroge donc chaque tenant avec son propre en-tête, à la racine.
- **Rotation contraignante pour le client** : renouveler un jeton révoque
  l'ancien ; l'Odoo du tenant doit recevoir la nouvelle fiche.
- **Suppression gardée** : refusée tant que le tenant porte des postes ou des
  lignes.
- **Solde VoIP.ms sur demande** : le tableau de bord ne relit le solde que par
  *Actualiser le solde* ; un chargement de page n'appelle jamais le fournisseur.
- **Pas de réglages propres** : le module n'a pas de `res.config.settings` ; URL
  et jeton administrateur sont ceux de `wazo_tenant`.

## Pistes

Aucune piste n'est consignée : le code ne porte aucun marqueur de travail en attente.
