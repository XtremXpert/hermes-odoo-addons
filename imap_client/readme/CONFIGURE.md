Le module n'ajoute pas d'écran de réglages : la connexion se règle sur chaque fiche de
compte, dans _Courriels_ > _Comptes_.

Deux groupes sont déclarés et s'attribuent dans l'onglet _Droits d'accès_ de la fiche
usager :

- **IMAP — Lecture** : lecture des comptes, dossiers et messages ;
- **IMAP — Gestionnaire** : en plus, création et suppression des comptes, test de
  connexion et synchronisation.

Le mot de passe IMAP est porté par la fiche du compte ; son champ n'est visible que du
groupe **IMAP — Gestionnaire** et il est stocké dans la base Odoo.

L'envoi des réponses passe par le serveur sortant configuré dans Odoo (_Réglages_ >
_Technique_ > _Courriel_ > _Serveurs sortants_, en mode développeur) : sans serveur
sortant, l'assistant de réponse ne peut pas envoyer.
