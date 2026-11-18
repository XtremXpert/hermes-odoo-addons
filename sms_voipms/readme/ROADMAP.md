## Limites connues

- Envoi seulement : les réponses des destinataires ne remontent pas dans Odoo.
- NANP (Canada / États-Unis) seulement.
- Pas d'accusé de livraison poussé par VoIP.ms : le SMS reste *Envoyé* jusqu'au
  nettoyage, sauf si le fournisseur confirme la livraison.
- `sms_twilio` et `sms_voipms` sont mutuellement exclusifs (même champ
  `sms_provider`).

## Évolutions envisagées

- Réponses entrantes : contrôleur HTTP, URL SMS du DID, rattachement au chatter
  à partir du suivi conservé à l'envoi.
- Accusés de livraison par interrogation périodique (`getSMS`).
