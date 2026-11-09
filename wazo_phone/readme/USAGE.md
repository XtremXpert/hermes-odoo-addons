Pour utiliser ce module, il faut :

1. Attribuer le groupe **Téléphonie Wazo : Utilisateur** (ou _Gestionnaire_) à
   l'usager, et lier son compte Odoo à un poste Wazo synchronisé.
2. Ouvrir _Téléphonie Wazo_ > _Tableau de bord_ : indicateurs sur 7, 30 ou 90 jours
   (appels, manqués, taux de réponse entrant, temps d'appel) pour son poste ; un
   gestionnaire voit en plus la section _Équipe_ et la répartition par poste.
3. Consulter _Téléphonie Wazo_ > _Journal d'appels_ (fourni par `wazo_tenant`) : sens,
   appelant, destination, appel répondu, durée et contact reconnu. Le journal est
   alimenté par la synchronisation, manuelle ou planifiée, pas en temps réel.
4. Si l'administrateur a activé le softphone, ouvrir le panneau par l'icône téléphone
   de la barre système : composer un numéro et cliquer **Appeler**, répondre avec
   **Répondre**, terminer avec **Raccrocher**. L'onglet _Journal_ du panneau liste les
   appels récents.
5. Cliquer **Appeler** sur un numéro dans n'importe quel champ téléphone d'Odoo
   (click-to-call) : l'appel part par le softphone si l'usager a un poste Wazo
   configuré, sinon par le lien `tel:` du navigateur.
6. En fin d'appel, une note est déposée sur la fiche du contact reconnu ; un appel
   entrant manqué crée une activité « Appel » et une notification.

Le pont softphone (activation, moteur, URL WebSocket, domaine SIP) se règle dans
_Réglages_ > _Téléphonie Wazo_.
