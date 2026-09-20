# Addons custom Odoo (Diverse-Cité)

Des modules Odoo maison écrits contre le build local d'Odoo 20
(`~/hermes-dev/odoo20/`, branche `main`).

## Modules

### `mailcow_admin`
Administration d'un serveur **Mailcow** (boîtes mail, domaines, alias)
via son API REST v1 (`X-API-Key`). 29 tests.

### `voipms_sms`
Envoi de **SMS** via l'API **VoIP.ms** (REST v1, `api_username`/`api_token`) :
DIDs, boîte d'envoi segmentée (150 car., format `n/N`), réglages, droits.
31 tests.

## Utilisation

1. Cloner le dépôt.
2. Ajouter le chemin à l'`addons_path` d'Odoo (ou copier chaque module).
3. Installer les modules :
   ```sh
   odoo-bin -d <db> -i mailcow_admin,voipms_sms --stop-after-init
   ```
4. Configurer : Réglages → **Mailcow** (URL + clé API) et Réglages →
   **SMS VoIP.ms** (utilisateur + token), puis tester la connexion.

## Tests

```sh
odoo-bin -d t_test -i mailcow_admin,voipms_sms \
  --test-tags=/mailcow_admin,/voipms_sms --stop-after-init --log-level=test
```

## Notes

- Développés en TDD contre Odoo 20 (dev/master). Les API changent vite sur
  cette branche : se référer à la skill `odoo20-breaking-changes` si une
  migration sur une autre version est nécessaire.
- Les secrets (clé Mailcow, token VoIP.ms) sont stockés dans
  `ir.config_parameter` (`mailcow.*` / `voipms.*`) — jamais dans le code.
