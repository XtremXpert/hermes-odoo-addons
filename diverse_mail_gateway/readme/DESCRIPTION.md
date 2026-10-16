Point d'entrée HTTP qui reçoit le courriel brut (RFC 5322) d'un relais externe et le
remet à `mail.thread.message_process`, comme le ferait le relèvement IMAP, mais sans
boîte à relever ni compte utilisateur : l'appel est authentifié par un **jeton**.

Son client principal est `relais-courriel`, le relais LMTP déployé à côté de Mailcow
(dépôt `diverse-odoo`, `infra/relais-courriel/`) : Postfix lui remet le courriel des
adresses d'Odoo, il le pousse ici et traduit la réponse en code SMTP.

## Routes

Toutes sous `/diverse/mail-gateway/`, en HTTPS seulement (sauf réglage contraire, voir
Configuration).

| Route | Authentification | Rôle |
| --- | --- | --- |
| `GET /health` | aucune | sonde de vie, répond toujours `200` |
| `POST /check` | jeton | vérifie le jeton, sans rien écrire |
| `POST /process` | jeton | remet le message brut à `message_process` |

En-têtes de `/process` :

| En-tête | Requis | Rôle |
| --- | --- | --- |
| `X-Mail-Gateway-Token` | oui | le jeton |
| `Content-Type` | oui | `message/rfc822` |
| `X-Mail-Gateway-Save-Original` | non | `1` : garder le message d'origine en pièce jointe |
| `X-Mail-Gateway-Strip-Attachments` | non | `1` : retirer les pièces jointes |

Réponses de `/process` :

| HTTP | Corps | Cas |
| --- | --- | --- |
| `200` | `{"ok": true, "result": <id>, "message_id": "<…>"}` | message remis à un fil |
| `400` | `{"ok": false, "error": "bad_request"}` | corps vide ou illisible |
| `401` | `{"ok": false, "error": "unauthorized"}` | jeton absent, invalide, expiré ou révoqué |
| `403` | `{"ok": false, "error": "forbidden"}` | requête en HTTP clair |
| `422` | `{"ok": false, "error": "no_route"}` | aucun alias ni fil ne correspond |
| `500` | `{"ok": false, "error": "internal"}` | erreur inattendue |

## Sécurité

- Le jeton (`secrets.token_urlsafe(32)`) n'est montré **qu'une fois**, à sa création :
  seule son empreinte SHA-256 est stockée, comparée en temps constant.
- Chaque jeton se révoque, peut expirer, et garde sa date et son adresse de dernier
  usage.
- Seul `message_process` s'exécute en superutilisateur : un jeton volé permet de créer
  des messages, pas de lire ni de modifier la base.
- Les journaux ne contiennent jamais le jeton.

## Origine

Fork renommé de `bemade_mail_gateway` (Bemade Inc., AGPL-3), porté sur Odoo 20.
