## Limites connues

- **Pas d'accusé de livraison** : l'état passe à `Envoyé` dès que `sendSMS`
  répond ; le module ne relit jamais le statut de remise (aucun appel de statut
  dans le client).
- **Pas de SMS entrants** : le client n'appelle que `sendSMS`, `getDIDsInfo` et
  `getBalance` ; aucun message reçu n'est rapatrié.
- **Synchronisation des DID fiche par fiche** : `action_sync_from_provider` part
  d'une fiche DID et aligne toute la liste, mais les menus n'exposent pas de
  bouton global de synchronisation.
- **Identifiants en clair** : `voipms.api_username` et `voipms.api_token` sont des
  champs de réglages stockés dans `ir.config_parameter`, et l'API les transporte
  en paramètres d'URL (requête GET), sans en-tête.
- **Segmentation bornée** : 150 caractères par segment, 1600 au total ; un mot
  plus long qu'un segment est coupé au milieu du mot.
- **Aucune tâche de fond** : pas de cron ni d'envoi différé ; un brouillon
  n'est envoyé que par *Envoyer*.
- **Statut `Beta`** : `development_status` vaut `Beta`.

## Pistes

Aucune piste n'est consignée : le code ne porte aucun marqueur de travail en attente.
