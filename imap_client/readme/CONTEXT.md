Odoo ne sait pas nativement lire une boîte IMAP sans passer par un serveur
entrant et un compte dédié. Ce module relie directement une boîte (serveur,
port, SSL, identifiants) à des fiches Odoo, pour consultation et réponse. Il est
distinct de `diverse_mail_gateway`, qui reçoit le courrier d'un relais par jeton
sans boîte, et de `mailcow`, qui administre un serveur : ici, on relève une
boîte avec `imaplib`.

La synchronisation procède par étapes : découverte des dossiers, puis
rapatriement des en-têtes des 50 derniers messages de chaque dossier, en
ignorant ceux déjà connus par leur Message-ID. Le corps n'est téléchargé qu'à la
demande (`Lire`), puis le message est marqué lu sur le serveur ; `Marquer lu`
pose le drapeau sans télécharger. Une réponse part par le serveur sortant
d'Odoo avec `In-Reply-To` et `References`, pour que le fil reste complet chez
le destinataire. Chaque courriel peut être ancré au contact reconnu par
l'adresse d'expédition, dans son fil.

Deux groupes suffisent : Lecture et Gestionnaire. La recherche est bornée par
`_search` aux comptes dont l'usager est propriétaire, sauf pour les
gestionnaires qui voient tout ; les actions de connexion et de synchronisation
vérifient le groupe dans la méthode, pas seulement sur le bouton. Le mot de
passe est porté par la fiche du compte et son champ n'est visible que du groupe
Gestionnaire. Aucune dépendance Python externe : `imaplib` est dans la
bibliothèque standard.

## Modèle de données

| Modèle | Champs clés | Relations |
| --- | --- | --- |
| `imap.account` | `name`, `host`, `use_ssl` | `folder_ids` → `imap.folder` (1-n). |
| `imap.folder` | `name`, `unread` | `account_id` → `imap.account` ; `message_ids` → `imap.message`. |
| `imap.message` | `message_id`, `subject`, `seen` | `folder_id` → `imap.folder` ; `res.partner` et `mail.message` (externes). |
| `imap.reply` | `to_addr`, `subject` | `message_id` → `imap.message` (1-n). |
