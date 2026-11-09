La synchronisation est manuelle et bornée : au plus 50 messages par dossier
(`LIMITE_SYNC`), et seuls les en-têtes sont rapatriés. Le corps n'est téléchargé
qu'à la demande, en texte ou en HTML ; les pièces jointes ne sont pas extraites
et ne sont pas conservées.

La date enregistrée sur `imap.message` est l'heure de la synchronisation, pas la
date de l'en-tête `Date` : le tri « plus récent d'abord » reflète donc l'ordre de
rapatriement, pas l'ordre réel des courriels.

Les dossiers ne sont jamais supprimés d'Odoo quand ils disparaissent du serveur,
et les messages ne sont jamais effacés du serveur par le module. Le seul drapeau
synchronisé est `\Seen` ; les autres drapeaux et le nombre de non-lus restent
ceux du serveur au moment du fetch.

Le mot de passe IMAP est stocké dans la base Odoo, lisible du seul groupe
Gestionnaire : ce n'est pas un coffre de secrets. L'envoi des réponses dépend
d'un serveur sortant configuré dans Odoo ; sans lui, l'assistant ne peut pas
envoyer.
