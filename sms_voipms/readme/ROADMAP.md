## Limites connues

- NANP (Canada / États-Unis) seulement.
- Aucun accusé de livraison : l'API VoIP.ms n'expose pas de statut
  d'acheminement, le SMS reste *Envoyé*.
- `sms_twilio` et `sms_voipms` sont mutuellement exclusifs (même champ
  `sms_provider`).
- Les réponses ne sont rattachées qu'aux envois encore présents (≤ 90 jours) ;
  au-delà, elles vont dans la file.

## Évolutions envisagées

- Accusés de livraison par interrogation périodique — impossible tant que
  VoIP.ms n'expose pas de statut (le champ `carrier_status` répond
  « Information not available »).
- Enregistrement A2P chez VoIP.ms si le volume de marketing augmente.
- Rattachement des réponses à des envois plus anciens (journal des envois).
