Pour utiliser ce module, il faut :

1. Avoir configuré `wazo_phone` et `voipms_sms` (URL et jeton Wazo, utilisateur et
   jeton VoIP.ms), et rendu le serveur Wazo joignable en SIP par VoIP.ms.
2. Ouvrir _Téléphonie Wazo_ > _Trunks VoIP.ms_ et créer un trunk : nom, protocole
   (_SIP_ ou _IAX2_), serveur (_POP_) VoIP.ms, identifiant et mot de passe du
   sous-compte (laisser vide pour les faire créer au provisionnement), indicatif
   d'appelant sortant et préfixe de sortie (par défaut `9`).
3. Cliquer **Provisionner** : le module crée le sous-compte SIP chez VoIP.ms, puis
   l'endpoint, le trunk et l'outcall côté Wazo. **Vérifier la connexion** contrôle
   l'enregistrement ; **Réessayer** reprend un provisionnement en erreur ; **Retirer**
   supprime le trunk du serveur (les numéros qui en dépendent cessent de sonner).
4. Pour les appels sortants, composer `<préfixe><numéro>` depuis un poste Wazo.
5. Pour router un DID entrant, ouvrir sa fiche dans _SMS VoIP.ms_ > _DIDs_ : le groupe
   _Pont Wazo (appels)_ apparaît sur la fiche, choisir le type de destination
   (utilisateur, groupe d'appel, file, menu vocal, conférence ou messagerie vocale)
   puis cliquer **Router vers Wazo**. Le module crée l'incall `from-extern` puis
   bascule le routage VoIP.ms. **Retirer le routage** remet le DID en `sys:hangup`.
