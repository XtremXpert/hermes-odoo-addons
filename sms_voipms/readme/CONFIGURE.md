## Prérequis VoIP.ms

1. Activer l'API dans le portail VoIP.ms (menu *SOAP and REST/JSON API*) et
   créer un jeton.
2. Autoriser l'adresse IP publique du serveur Odoo dans la liste blanche de
   l'API.
3. Activer le SMS sur le DID expéditeur (*DID Numbers* → *SMS*).

## Réglages Odoo

1. Réglages → section **SMS VoIP.ms** : renseigner l'utilisateur API et le
   jeton, puis *Tester la connexion*.
2. Réglages → **SMS** : choisir « Envoyer via VoIP.ms » et le **DID
   expéditeur**.
3. Enregistrer.

Pour revenir au service Odoo, choisir « Envoyer via Odoo (IAP) » : les crédits
IAP redeviennent la voie d'envoi, sans réinstallation.

Le DID proposé est limité aux numéros dont le SMS est activé chez VoIP.ms
(champ `sms_enabled` synchronisé par `voipms_sms`, menu *SMS VoIP.ms →
Synchroniser les DID*).

## Réponses entrantes

1. L'instance Odoo doit être joignable en HTTPS depuis Internet (c'est le cas
   du staging et de la production maison).
2. Réglages → **SMS**, bloc VoIP.ms : le **jeton de rappel** est généré à
   l'ouverture ; l'**URL de rappel** affichée contient le jeton et les
   placeholders `{FROM}`, `{TO}`, `{MESSAGE}`.
3. Cliquer **Configurer l'URL SMS du DID** : le module appelle `setSMS` sur le
   DID expéditeur (`enable=1`, `url_callback`, `url_callback_enabled=1`,
   `url_callback_retry=1`).
4. Vérifier en répondant au SMS depuis le téléphone : la réponse apparaît dans
   le chatter de l'enregistrement d'origine ou dans *SMS VoIP.ms → Réponses
   entrantes*. Un « STOP » ajoute le numéro à la liste noire téléphonique.
