Pour utiliser ce module, il faut :

1. Se connecter à Odoo avec un compte membre du groupe _Administration / Paramètres_
   (`base.group_system`).
2. Ouvrir l'interface de l'agent à l'adresse `https://<hôte Odoo>/hermes/n1/` (ou
   `/hermes/n2/`, `/hermes/n3/`) : le tableau de bord renvoie le navigateur vers
   `/hermes/sso/authorize` sur Odoo.
3. Laisser Odoo autoriser la demande : il vérifie la session et les droits, émet un
   code à usage unique valable 60 secondes et redirige vers l'URL de retour exacte du
   tableau de bord (`/hermes/<niveau>/auth/callback`), qui échange ensuite ce code
   contre sa propre session d'une heure.
4. En secours, la connexion par mot de passe du tableau de bord reste disponible sur
   `/hermes/<niveau>/login?password=1`.

Un compte non administrateur est refusé (`403`) ; une URL de retour étrangère, un
niveau inconnu ou un défi PKCE absent sont refusés (`400`). Aucun mot de passe Odoo
n'atteint le tableau de bord.
