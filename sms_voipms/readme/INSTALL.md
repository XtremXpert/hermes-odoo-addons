## Dépendances

- Odoo 20.0 Community.
- Module `voipms_sms` (client REST, segmentation, DID) — installé
  automatiquement comme dépendance.
- Module `sms` (framework SMS d'Odoo).
- Un compte VoIP.ms avec l'API activée, un jeton, et un DID dont le SMS est
  activé.

Aucune bibliothèque Python supplémentaire n'est exigée : le client utilise
`urllib` de la bibliothèque standard. `phonenumbers` (fourni par
`phone_validation` et par l'image maison) améliore la reconnaissance du
contact (`phone_sanitized`) ; sans lui, le module compare les chiffres du
champ `phone` (repli) et la recherche reste fonctionnelle.
