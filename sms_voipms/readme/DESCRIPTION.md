Envoie les SMS d'Odoo par l'API REST de **VoIP.ms** au lieu du service payant
IAP d'Odoo.

Le réglage se fait par société : « Envoyer via Odoo (IAP) » (défaut) ou
« Envoyer via VoIP.ms ». Dans le second cas, le composeur SMS, le CRM, les
modèles de SMS, l'automatisation et le marketing de masse passent tous par
VoIP.ms, et le DID expéditeur est choisi dans les réglages de la société.

Le module s'appuie sur `voipms_sms` (client REST, segmentation à 150 caractères,
gestion des DID, identifiants API) et sur l'abstraction fournisseur d'Odoo 20 —
la même que celle utilisée par `sms_twilio`.

Limites connues :

- **envoi seulement** : les réponses des destinataires ne remontent pas dans
  Odoo (une spec ultérieure pourra les rattacher au chatter à partir du suivi
  conservé à l'envoi) ;
- **NANP seulement** (Canada / États-Unis) ;
- `sms_twilio` et `sms_voipms` déclarent tous deux le champ `sms_provider` :
  les installer ensemble fait perdre une option de la sélection (limite d'Odoo
  20 pour les modules fournisseurs), donc ne pas installer les deux.
