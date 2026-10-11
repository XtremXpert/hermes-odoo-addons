Permet à un administrateur déjà connecté à Odoo d'ouvrir le tableau de bord d'un agent Hermes (`/hermes/n1/`, `/hermes/n2/`, `/hermes/n3/` sur le même hôte) sans seconde connexion. Odoo sert de fournisseur d'identité, selon le flux OAuth 2 par code avec PKCE.

## Fonctionnement

1. Le tableau de bord envoie le navigateur sur `/hermes/sso/authorize` avec le niveau, son URL de retour, un `state` et un défi PKCE `S256`.
2. La route exige une session Odoo d'**administrateur** (`base.group_system`) et n'accepte que l'URL de retour exacte `https://<cet hôte>/hermes/<niveau>/auth/callback`. Elle crée un code à usage unique valable 60 secondes, stocké haché, et redirige vers le tableau de bord.
3. Le tableau de bord échange le code de serveur à serveur sur `/hermes/sso/token` avec le vérificateur PKCE. Le code ne sert qu'une fois, même en cas de refus ; l'expiration, le niveau, l'URL de retour et le vérificateur sont contrôlés, et les droits d'administrateur sont revérifiés.

Le tableau de bord émet ensuite sa propre session d'une heure (fournisseur `odoo` de hermes-guardrails, `agent-deploy/level2/dashboard/odoo_sso.py`). Aucun mot de passe ni session Odoo n'atteint le pod de l'agent. La connexion par mot de passe du tableau de bord reste disponible en secours sur `/hermes/<niveau>/login?password=1`.

## Données

Le modèle `hermes.dashboard.sso.code` n'est lu et écrit que par les deux routes, en `sudo` ; aucun droit d'accès n'est accordé aux utilisateurs. Les codes expirés depuis plus d'une heure sont supprimés automatiquement.

## Tests

```sh
ADDONS=addons tools/test-modules.sh IMAGE hermes_dashboard_sso
```

Les tests couvrent l'échange unique du code, le refus d'un non-administrateur, d'une URL de retour étrangère ou d'un autre niveau, et la perte des droits entre l'autorisation et l'échange.
