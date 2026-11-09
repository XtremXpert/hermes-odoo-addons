Relie une boîte courriel IMAP à Odoo : le module crée des fiches de compte (serveur,
port, SSL, identifiants), découvre les dossiers de la boîte et rapatrie les en-têtes des
derniers messages.

La synchronisation, réservée aux gestionnaires, rapatrie au plus 50 messages par dossier
et ignore ceux déjà connus par leur Message-ID. Le corps d'un message n'est téléchargé
qu'à l'ouverture (_Lire_) ; le message est alors marqué lu sur le serveur. Une réponse
part par le serveur sortant d'Odoo, avec les en-têtes `In-Reply-To` et `References`,
pour que le fil reste complet chez le destinataire.

Chaque courriel rapatrié peut être ancré au contact Odoo reconnu par son adresse
d'expédition, dans le fil du contact. La connexion s'appuie sur `imaplib` de la
bibliothèque standard : aucune dépendance Python externe.
