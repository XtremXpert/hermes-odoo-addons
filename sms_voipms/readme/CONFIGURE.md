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
(champ `sms_enabled` synchronisé par `voipms_sms`).
