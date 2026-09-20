# Addons custom Odoo (Diverse-Cité)

Des modules Odoo maison écrits contre le build local d'Odoo 20
(`~/hermes-dev/odoo20/`, branche `main`).

## Architecture télécom

```
VoIP.ms ──SIP trunk──► FreePBX (Asterisk, LXC Proxmox)
    │                       │
    └── REST (SMS) ────────► Odoo   ← voipms_sms (direct, fiable)
FreePBX ── ARI ───────────► Odoo   ← asterisk_ari (voix / click-to-call)
```

- Le **SMS** passe en **REST direct** vers l'API VoIP.ms (`voipms_sms`) —
  c'est la voie la plus fiable, sans hop SIP.
- La **voix** (IVR, files, transfert, vocaux, fax T.38) passe par **FreePBX** ;
  Odoo pilote les appels via l'**API ARI** d'Asterisk (`asterisk_ari`).

## Modules

### `mailcow_admin`
Administration d'un serveur **Mailcow** (boîtes mail, domaines, alias)
via son API REST v1 (`X-API-Key`). 29 tests.

### `voipms_sms`
Envoi de **SMS** via l'API **VoIP.ms** (REST v1, `api_username`/`api_token`) :
DIDs, boîte d'envoi segmentée (150 car., format `n/N`), réglages, droits.
31 tests.

### `asterisk_ari`
**Click-to-call** et suivi d'appels via l'**API ARI** d'Asterisk/FreePBX :
bouton « Appeler » sur la fiche partenaire, historique des appels
(état, ID ARI, erreurs), réglages + test de connexion. 26 tests.

## Utilisation

1. Cloner le dépôt.
2. Ajouter le chemin à l'`addons_path` d'Odoo (ou copier chaque module).
3. Installer les modules :
   ```sh
   odoo-bin -d <db> -i mailcow_admin,voipms_sms,asterisk_ari --stop-after-init
   ```
4. Configurer :
   - Réglages → **Mailcow** (URL + clé API)
   - Réglages → **SMS VoIP.ms** (utilisateur + token)
   - Réglages → **Téléphonie (Asterisk ARI)** (URL ARI + application + jeton)
   
   Puis tester chaque connexion.

## Tests

```sh
odoo-bin -d t_test -i mailcow_admin,voipms_sms,asterisk_ari \
  --test-tags=/mailcow_admin,/voipms_sms,/asterisk_ari \
  --stop-after-init --log-level=test
```

## Notes

- Développés en TDD contre Odoo 20 (dev/master). Les API changent vite sur
  cette branche : se référer à la skill `odoo20-breaking-changes` si une
  migration sur une autre version est nécessaire.
- Les secrets (clé Mailcow, token VoIP.ms, jeton ARI) sont stockés dans
  `ir.config_parameter` (`mailcow.*` / `voipms.*` / `asterisk_ari.*`) —
  jamais dans le code.
- `asterisk_ari` (M1) utilise le REST ARI uniquement. Le **WebSocket ARI**
  ( événements temps réel : réponse, fin d'appel → mise à jour de l'état)
  est prévu en M2.
