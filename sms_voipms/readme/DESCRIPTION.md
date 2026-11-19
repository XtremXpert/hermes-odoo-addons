Envoie les SMS d'Odoo par l'API REST de **VoIP.ms** au lieu du service payant
IAP d'Odoo, et reçoit les réponses.

Le réglage se fait par société : « Envoyer via Odoo (IAP) » (défaut) ou
« Envoyer via VoIP.ms ». Dans le second cas, le composeur SMS, le CRM, les
modèles de SMS, l'automatisation et le marketing de masse passent par VoIP.ms,
et le DID expéditeur est choisi dans les réglages de la société.

Les **réponses entrantes** arrivent par l'URL de rappel du DID
(`url_callback`) : elles sont postées dans le chatter de l'enregistrement
d'origine (dernier SMS envoyé, ≤ 90 jours), sinon dans la file « Réponses
entrantes ». Un **STOP** (STOP, ARRET, DÉSABONNER…) ajoute le numéro à la liste
noire téléphonique d'Odoo — comportement d'Odoo : le composeur de masse
l'exclut, les envois manuels restent possibles, aucune confirmation n'est
envoyée.

Le module s'appuie sur `voipms_sms` (client REST, segmentation à 150 caractères,
gestion des DID, identifiants API) et sur l'abstraction fournisseur d'Odoo 20 —
la même que celle utilisée par `sms_twilio`.

Limites connues :

- **NANP seulement** (Canada / États-Unis) ;
- **aucun accusé de livraison** : l'API VoIP.ms n'expose pas de statut
  d'acheminement, le SMS reste « Envoyé » (en attente) — les statistiques de
  marketing ne montrent pas de « Livré » ;
- `sms_twilio` et `sms_voipms` déclarent tous deux le champ `sms_provider` :
  les installer ensemble fait perdre une option de la sélection (limite d'Odoo
  20 pour les modules fournisseurs), donc ne pas installer les deux.
