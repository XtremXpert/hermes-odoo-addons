Pour utiliser ce module, il faut :

1. Attribuer le groupe **Utilisateur SMS** (ou **Gestionnaire SMS**, qui l'implique)
   aux usagers : le menu _SMS VoIP.ms_ est réservé à ce groupe.
2. Ouvrir _SMS VoIP.ms_ > _DIDs_ et cliquer **Synchroniser depuis VoIP.ms** sur une
   fiche DID : la liste locale est alignée sur les numéros du compte VoIP.ms, avec
   _SMS disponible_ et _SMS activé_.
3. Créer un message dans _SMS VoIP.ms_ > _Boîte d'envoi_ : choisir le _DID (émetteur)_,
   saisir le _Destinataire_ (numéro NANP, 10 chiffres ou préfixe `1`) et le _Message_,
   puis cliquer **Envoyer**.
4. Un message de plus de 150 caractères est découpé en segments numérotés `n/N` ; un
   message vide, non NANP ou de plus de 1600 caractères est refusé avant tout appel.
5. La boîte d'envoi garde l'historique : état, date d'envoi, identifiants de message
   VoIP.ms et, en cas d'échec, le message d'erreur.

Le jeton et l'utilisateur de l'API se règlent dans Réglages (voir Configuration).
