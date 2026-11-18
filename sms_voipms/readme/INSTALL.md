## Dépendances

- Odoo 20.0 Community.
- Module `voipms_sms` (client REST, segmentation, DID) — installé
  automatiquement comme dépendance.
- Module `sms` (framework SMS d'Odoo).
- Un compte VoIP.ms avec l'API activée, un jeton, et un DID dont le SMS est
  activé.

Aucune bibliothèque Python supplémentaire : le client existant utilise `urllib`
de la bibliothèque standard.
