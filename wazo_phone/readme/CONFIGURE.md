1. Inscrire les utilisateurs aux groupes du module : les menus sont rangés derrière eux
   et l'administrateur n'y est **pas** d'office. Le groupe « Téléphonie Wazo :
   Gestionnaire » implique « Utilisateur ».
2. Dans Réglages → **Téléphonie Wazo**, renseigner l'URL du serveur, le jeton d'API et
   le tenant, puis tester la connexion. Côté tenant, le jeton est le **jeton de tenant**
   fabriqué par `wazo_server`.

## Softphone dans le navigateur (pont voip)

La section « Pont softphone » des réglages n'apparaît que si le module `voip`
d'Enterprise est installé et que le serveur Wazo expose le transport `wss` :

- **Softphone (voip)** : active le pont (paramètre `wazo.softphone_enabled`,
  vrai par défaut) ; les champs suivants sont masqués quand il est faux.
- **URL WebSocket (wss)** : `wazo.ws_url` ; à défaut, l'URL est dérivée de
  `wazo.url` (voie native v3, endpoint `/api/asterisk/ws`).
- **Domaine SIP (PBX)** : `wazo.pbx_domain`, utilisé dans les URI SIP ;
  « asterisk » par défaut.
- **Créer le provider et propager les identifiants** : crée ou met à jour le
  provider « Wazo » et réapplique les identifiants SIP des utilisateurs
  synchronisés.
