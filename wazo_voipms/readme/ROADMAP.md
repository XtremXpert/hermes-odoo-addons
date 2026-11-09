## Limites connues

- **Un protocole par trunk** : un sous-compte VoIP.ms est mono-protocole
  (`protocol` : SIP ou IAX2, mesuré) ; faire cohabiter SIP et IAX2 demande deux
  trunks.
- **Routage entrant en deux moitiés** : l'incall est créé côté Wazo, puis le
  routage est basculé chez VoIP.ms (`setDIDRouting`). Les deux appels ne sont pas
  transactionnels : un échec partiel peut laisser un incall sans routage, que la
  reprise idempotente rattrape.
- **SIP entrant exposé** : le routage en `sip:` exige que Wazo soit joignable
  publiquement (port 5060/5061) ; IAX2 évite le port ouvert en passant par
  l'enregistrement.
- **Une destination par DID** : la contrainte n'accepte qu'un seul des champs de
  destination (utilisateur, groupe, file, IVR, conférence, messagerie).
- **Retrait destructeur pour les numéros** : *Retirer* supprime le trunk du
  serveur ; les numéros qui en dépendent cessent de sonner (`readme/USAGE.md`).
- **Secrets SIP en clair** : `voipms_password` est un `Char` réservé au groupe
  gestionnaire, stocké sans chiffrement dans la base.
- **Aucune tâche de fond** : provisionnement, vérification et routage sont des
  gestes manuels ; pas de cron.

## Pistes

Aucune piste n'est consignée : le code ne porte aucun marqueur de travail en attente.
