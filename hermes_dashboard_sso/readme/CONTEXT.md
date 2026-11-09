Les tableaux de bord des agents Hermes (N1, N2, N3) sont servis par des pods
distincts d'Odoo. Sans passerelle, un administrateur devrait s'y connecter une
seconde fois. Ce module fait d'Odoo le fournisseur d'identité, selon le flux
OAuth 2 par code avec PKCE ; il est séparé de `hermes_activity`, qui vit dans
Discuss, et des tableaux de bord eux-mêmes, qui restent hors d'Odoo.

Le flux tient en deux routes : `/hermes/sso/authorize` exige une session
administrateur (`base.group_system`), n'accepte qu'une URL de retour égale à
`https://<cet hôte>/hermes/<niveau>/auth/callback`, puis émet un code à usage
unique valable 60 secondes, stocké haché. `/hermes/sso/token`, en `auth="none"`,
échange ce code contre l'identité du porteur, à condition que le vérificateur
PKCE S256 corresponde, que le niveau et l'URL de retour soient ceux de
l'autorisation, et que l'utilisateur soit toujours administrateur actif. Un code
est brûlé même quand l'échange est refusé.

Aucun mot de passe ni session Odoo n'atteint le pod de l'agent : le tableau de
bord émet ensuite sa propre session d'une heure, et la connexion par mot de
passe reste disponible en secours. Le modèle `hermes.dashboard.sso.code` n'est
manipulé que par les deux routes, en `sudo` ; son ACL ne donne accès qu'à
`base.group_system`. Un autovacuum supprime les codes expirés depuis plus d'une
heure.

## Modèle de données

| Modèle | Champs clés | Relations |
| --- | --- | --- |
| `hermes.dashboard.sso.code` | `code_hash`, `level`, `expires_at` | Aucune relation interne ; `user_id` pointe vers `res.users` (externe). |
