Le courrier entrant d'Odoo arrive normalement par un relèvement IMAP, avec une
boîte et un compte utilisateur à gérer. Ici, un relais LMTP externe
(`relais-courriel`) reçoit déjà le courrier des adresses Odoo : il lui faut un
point d'entrée HTTP qui le remette à `message_process`, authentifié par un
jeton et non par une session. D'où un module séparé de `imap_client`, qui
relève une boîte, et de `mailcow`, qui administre un serveur de messagerie.

Trois routes sous `/diverse/mail-gateway/` : `health` sans authentification,
`check` et `process` protégées par l'en-tête `X-Mail-Gateway-Token`. Le jeton
n'est jamais stocké en clair : seule son empreinte SHA-256 est conservée, et la
comparaison parcourt toute la liste des jetons actifs en temps constant, sans
sortie anticipée. Seul `message_process` tourne en superutilisateur ; un jeton
volé permet donc de créer des messages, pas de lire la base. Le HTTPS est
exigé, sauf paramètre `diverse_mail_gateway.allow_http` pour un banc d'essai.

Le code de réponse est traduit en décision SMTP par le relais : 200 livré,
422 aucune route, 401 jeton invalide ou expiré, 400 corps illisible, 500 erreur
interne. Le module est un fork renommé de `bemade_mail_gateway`
(Bemade Inc., AGPL-3) porté sur Odoo 20 ; il dépend de `base` et `mail` et
n'ajoute aucune dépendance Python.

## Modèle de données

| Modèle | Champs clés | Relations |
| --- | --- | --- |
| `diverse.mail_gateway.token` | `name`, `token_hash`, `active`, `expires_at` | Source des jetons du module. |
| `diverse.mail_gateway.token.create.wizard` | `name`, `generated_token` | `generated_token_id` → `diverse.mail_gateway.token` (1-n). |
