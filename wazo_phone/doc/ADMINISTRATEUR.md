# Guide administrateur — Téléphonie Wazo

Module Odoo **`wazo_phone`** (« Téléphonie Wazo ») : connecteur **Wazo Platform**
(wazo.io) pour Odoo 20. Il relie un serveur Wazo à Odoo :

- synchronisation des **utilisateurs** (poste, ligne SIP, endpoint WebRTC, messagerie
  vocale, compte SIP d'authentification) ;
- **journal d'appels** (CDR) importé depuis `wazo-call-logd` ;
- **softphone WebRTC** (pont optionnel vers le module « voip » d'Enterprise).

> Convention : le code du module est en anglais, la documentation et les libellés
> d'interface en français.

---

## 1. À quoi sert ce module

| Fonction         | Côté Odoo                                           | Côté Wazo                                                            |
| ---------------- | --------------------------------------------------- | -------------------------------------------------------------------- |
| Utilisateurs     | modèle miroir `wazo.user` + onglet Contact          | confd 1.1 (utilisateurs, lignes, extensions, endpoints, messageries) |
| Journal d'appels | modèle `wazo.cdr` (lecture seule)                   | call-logd 1.0                                                        |
| Comptes SIP      | identifiants stockés sur `wazo.user`                | authd 0.1                                                            |
| Softphone        | pont `voip.provider` + identifiants sur `res.users` | transport `wss` d'Asterisk                                           |

Versions d'API Wazo **26** utilisées par le client :

- `confd` → `/api/confd/1.1`
- `call-logd` → `/api/call-logd/1.0`
- `auth` (authd) → `/api/auth/0.1`

---

## 2. Prérequis

### 2.1 Serveur Wazo

- Un serveur **Wazo Platform 26** joignable en HTTPS.
- Un **token API** généré dans Wazo (compte avec droits de configuration).
- En environnement **multi-tenant** : l'UUID du tenant (en mono-tenant, laisser vide).

### 2.2 (Optionnel) Softphone WebRTC

- Le module **« voip »** d'Odoo **Enterprise** installé (sinon le pont est un no-op : le
  module fonctionne avec des postes SIP classiques).
- Le **transport WebSocket (wss)** d'Asterisk actif sur Wazo (point d'accès
  `wss://<hote>/api/asterisk/ws`).

---

## 3. Installation

1. Placer le module dans l'arborescence de modules personnalisés (`addons_path`).
2. Dans Odoo : **Paramètres → Applications** → rechercher **Téléphonie Wazo** →
   **Installer**.
3. Le module crée :
   - 2 rôles : _Utilisateur_ et _Gestionnaire_ ;
   - le menu **Téléphonie Wazo** (Tableau de bord, Utilisateurs, Journal d'appels) ;
   - un onglet **Téléphonie Wazo** sur la fiche Contact ;
   - un bloc de réglages sous **Paramètres → Applications → Téléphonie Wazo** ;
   - un cron « synchronisation du journal d'appels » (**désactivé par défaut**).

> Le module dépend de `base`, `web` et `mail` (ce dernier pour les notes et
> activités du bouclage d'appel, et le bus des notifications) : il s'installe
> sans Enterprise. Le softphone embarque son propre moteur (SDK officiel
> Wazo) ; le pont « voip » historique reste un no-op optionnel.

---

## 4. Réglages de connexion

**Paramètres → Applications → Téléphonie Wazo** (rôle _Gestionnaire_).

| Champ                          | Paramètre stocké          | Défaut / exemple                            |
| ------------------------------ | ------------------------- | ------------------------------------------- |
| URL du serveur Wazo            | `wazo.url`                | `https://wazo.diverse-cite.com`             |
| Token API Wazo                 | `wazo.api_key`            | token généré dans Wazo                      |
| Tenant (optionnel)             | `wazo.tenant_id`          | UUID du tenant, vide si mono-tenant         |
| Contexte des lignes            | `wazo.line_context`       | `default`                                   |
| Langue des messageries vocales | `wazo.voicemail_language` | `fr_CA`                                     |
| Tester la connexion            | — (bouton)                | appel en lecture seule `GET /users?limit=1` |

Cliquez **Tester la connexion** pour vérifier l'URL, le token et le tenant avant de
synchroniser le moindre utilisateur. En cas d'échec, le message d'erreur indique l'étape
(URL/token incomplet, HTTP 401, serveur injoignable…).

### Bloc softphone (identique écran, section « Softphone (module voip) »)

| Champ                                          | Paramètre stocké         | Note                             |
| ---------------------------------------------- | ------------------------ | -------------------------------- |
| Activer le pont softphone                      | `wazo.softphone_enabled` | vrai par défaut                  |
| URL WebSocket (wss)                            | `wazo.ws_url`            | ex `wss://wazo.diverse-cite.com` |
| Domaine SIP (PBX)                              | `wazo.pbx_domain`        | ex `wazo.diverse-cite.com`       |
| Créer le provider et propager les identifiants | — (bouton)               | ré-applique les identifiants SIP |

Si **URL WebSocket** est laissée vide, elle est **dérivée** de l'URL Wazo :
`https://hote[:port]` → `wss://hote[:port]/api/asterisk/ws`.

---

## 5. Rôles et permissions

| Rôle                               | Accès                                                                                  |
| ---------------------------------- | -------------------------------------------------------------------------------------- |
| **Téléphonie Wazo : Utilisateur**  | lecture `wazo.user` et `wazo.cdr` ; menu + onglet Contact                              |
| **Téléphonie Wazo : Gestionnaire** | CRUD complet ; réglages de connexion ; boutons de création/suppression/synchronisation |

Le gestionnaire inclut l'utilisateur (`implied_ids`).

---

## 6. Utilisateurs Wazo

### 6.1 Créer un utilisateur

Deux portes d'entrée :

**A. Depuis un Contact** (recommandé)

1. Ouvrir le **Contact**, onglet **Téléphonie Wazo**.
2. Renseigner le champ **Téléphone** (le poste Wazo en est dérivé).
3. Bouton **Créer utilisateur Wazo** → crée le miroir `wazo.user` (poste = chiffres du
   téléphone) et **synchronise immédiatement** sur Wazo.

**B. Depuis le menu Téléphonie Wazo → Utilisateurs**

1. **Nouveau** → nom, contact (optionnel), **poste** (chiffres).
2. Bouton **Synchroniser sur Wazo**.

### 6.2 États de l'utilisateur (`wazo_state`)

| État     | Badge                | Signification                                                              |
| -------- | -------------------- | -------------------------------------------------------------------------- |
| `new`    | _Nouveau_ (orange)   | pas encore synchronisé ; bouton « Synchroniser sur Wazo »                  |
| `synced` | _Synchronisé_ (vert) | ressources créées ; bouton « Supprimer les ressources Wazo »               |
| `error`  | _Erreur_ (rouge)     | dernier échec ; bouton « Réessayer la synchronisation » + message d'erreur |

> **Pattern Odoo 20** : en cas d'échec, l'état `error` et le message sont écrits sur la
> ligne (pas de `raise` après `write`), pour que l'erreur reste visible après rollback
> transactionnel.

### 6.3 Flux de synchronisation (côté Wazo 26)

`action_sync_wazo()` exécute, en séquence :

1. `POST /extensions` — le **poste** (idempotent : réutilisé s'il existe).
2. `POST /lines` — la **ligne SIP**, corps complet :
   - `context`, `extensions: [{exten}]`,
   - `endpoint_sip` **WebRTC-capable** (voir §8) : `auth_section_options` (username =
     poste) + `endpoint_section_options` (contexte + codecs).
3. `POST /users` — l'**utilisateur** (prénom/nom déduits du nom).
4. `PUT /users/{id}/lines/{id}` — association utilisateur ↔ ligne.
5. `POST /voicemails` — la **messagerie vocale** (nom, poste, contexte, langue).
6. `PUT /users/{id}/voicemails/{id}` — association utilisateur ↔ messagerie.
7. `POST /api/auth/0.1/users` — le **compte SIP d'authentification** (username = poste,
   mot de passe de registration généré localement et stocké). Idempotent : un compte
   existant (HTTP 409) est récupéré par son username.

À l'issue, `wazo.user` porte : `remote_user_id`, `remote_line_id`,
`remote_extension_id`, `sip_username`, `sip_password`, `remote_sip_id` (UUID authd).

### 6.4 Identifiants SIP

- `sip_username` = le **poste**.
- `sip_password` = mot de passe de **registration** (visible uniquement au rôle
  _Gestionnaire_, champ masquable). Utilisable dans un poste SIP classique.

### 6.5 Suppression des ressources Wazo

Bouton **Supprimer les ressources Wazo** (état `synced`). Ordre sûr (Wazo 26),
idempotent (404 ignorés), chaque relance après un échec partiel nettoie proprement :

1. `DELETE /lines/{id}?recursive=true` — ligne (retire endpoint, extensions,
   associations).
2. `DELETE /users/{id}/voicemails` — **dissociation** messagerie de l'utilisateur (route
   sans identifiant de messagerie), puis `DELETE /voicemails/{id}`.
3. `DELETE /users/{id}` — utilisateur.
4. `DELETE /extensions/{id}` — poste.
5. `DELETE /api/auth/0.1/users/{uuid}` — compte SIP d'auth **par UUID**.

Enfin : l'état revient à `new` et les identifiants distants sont effacés.

> ⚠️ **Référence circulaire** : une messagerie vocale ne peut être supprimée tant
> qu'elle est associée à un utilisateur, et un utilisateur ne peut être supprimé tant
> qu'il est associé à une ligne/messagerie. La dissociation
> `DELETE /users/{id}/voicemails` est l'étape clé qui casse cette boucle.

---

## 7. Journal d'appels (CDR)

Modèle `wazo.cdr` (lecture seule, `create/edit/delete=false`).

| Champ                                  | Source call-logd 1.0                         |
| -------------------------------------- | -------------------------------------------- |
| `wazo_cdr_id`                          | `id` (contrainte d'unicité)                  |
| `date_start` / `date_end`              | `start` / `end` (ISO-8601 → UTC)             |
| `answered`                             | `answered`                                   |
| `duration` (s)                         | `duration`                                   |
| `caller_num` / `caller_name`           | `source_extension` / `source_name`           |
| `destination_num` / `destination_name` | `destination_extension` / `destination_name` |
| `call_direction`                       | `call_direction` (Sortant/Entrant/Interne)   |
| `partner_id`                           | contact Odoo identifié (voir ci-dessous)     |

### Synchronisation

- **Manuelle** : formulaire du journal → bouton **Synchroniser les 24 dernières heures**
  (rôle Gestionnaire) → ouvre la liste filtrée sur la période.
- **Planifiée** : cron `cron_sync_cdrs` (1 h, **désactivé par défaut**). Pour l'activer
  : **Réglages → Planification** → activer la tâche « Téléphonie Wazo : synchronisation
  du journal d'appels ».

La pagination est bornée (200/appel, max 50 pages) ; un upsert par `wazo_cdr_id` rend la
synchronisation ré-exécutable sans doublons.

### Identification du contact Odoo

Pour chaque appel, le module cherche le contact concerné :

1. **Poste Wazo** d'abord (numéros courts) : `res.partner` dont `wazo_user_id.extension`
   correspond.
2. Sinon le **téléphone du contact** (numéros longs), matching tolérant aux séparateurs
   (espaces, tirets, points, parenthèses) ; seuls les numéros à ≥ 7 chiffres sont
   retenus pour éviter les faux positifs.

---

## 8. Softphone WebRTC (pont optionnel)

Actif seulement si : le module « **voip** » Enterprise est installé **et**
`wazo.softphone_enabled` est vrai **et** une URL WebSocket est configurée (explicitement
ou dérivée).

### 8.1 Activation

1. Renseigner **URL WebSocket (wss)** et **Domaine SIP (PBX)** (ou laisser l'URL
   dérivée).
2. Bouton **Créer le provider et propager les identifiants** → crée (ou met à jour) le
   `voip.provider` « **Wazo** » (`ws_server`, `pbx_ip`, `mode=prod`) et ré-applique les
   identifiants SIP des utilisateurs synchronisés vers leurs `res.users`.

### 8.2 Endpoints WebRTC

Le payload `endpoint_sip` généré réplique le template SIP **webrtc** de Wazo (codecs +
négociation + chiffrement) :

| Option             | Valeur                             |
| ------------------ | ---------------------------------- |
| `allow` (codecs)   | `opus,g722,alaw,ulaw,vp9,vp8,h264` |
| `ice_support`      | `yes`                              |
| `use_avpf`         | `yes`                              |
| `media_encryption` | `dtls`                             |
| `dtls_verify`      | `no`                               |
| `direct_media`     | `yes`                              |

Le transport `wss` est hérité de l'endpoint. L'authentification SIP porte `username` =
poste.

### 8.3 Propagation / révocation

- **Propagation** (`_propagate_voip_credentials`) : à chaque sync réussie, écrit
  `voip_provider_id`, `voip_username`, `voip_secret` sur chaque `res.users` du contact
  lié. **Non bloquant** : un échec du pont est loggé sans annuler la sync Wazo
  (définitive côté serveur).
- **Révocation** (`_revoke_voip_credentials`) : à la suppression, efface les
  identifiants **uniquement** s'ils proviennent de Wazo (username identique).

> **Licence** : Browser-Phone (référence d'intégration WebRTC) est **AGPL-3.0**. Ce
> module reste **LGPL-3** ; le pont repose sur le module « voip » d'Odoo Enterprise,
> sans embarquer de code Browser-Phone.

---

## 9. Paramètres de configuration (récapitulatif)

| Clé `ir.config_parameter` | Rôle                                        |
| ------------------------- | ------------------------------------------- |
| `wazo.url`                | URL HTTPS du serveur Wazo                   |
| `wazo.api_key`            | token API (en-tête `X-Auth-Token`)          |
| `wazo.tenant_id`          | tenant (en-tête `Wazo-Tenant`), optionnel   |
| `wazo.line_context`       | contexte des lignes/postes                  |
| `wazo.voicemail_language` | langue des messageries                      |
| `wazo.softphone_enabled`  | active le pont softphone                    |
| `wazo.ws_url`             | URL WebSocket SIP (optionnel, dérivé sinon) |
| `wazo.pbx_domain`         | domaine SIP du PBX                          |

> **Sécurité** : aucun jeton en clair dans le code. Les valeurs vivent dans
> `ir.config_parameter` (ou `res.config.settings`) ; le client les lit au runtime.
> L'authentification Wazo passe par `X-Auth-Token` et `Wazo-Tenant`.

---

## 10. Dépannage

| Symptôme                           | Cause probable / action                                                                    |
| ---------------------------------- | ------------------------------------------------------------------------------------------ |
| « Connexion Wazo incomplète »      | `wazo.url` ou `wazo.api_key` vide → renseigner les réglages.                               |
| Test de connexion HTTP 401/403     | token invalide ou tenant erroné → régénérer le token, vérifier `wazo.tenant_id`.           |
| Test de connexion « injoignable »  | URL/URL TLS incorrect, réseau, ou port non ouvert.                                         |
| État `error` à la sync             | lire `error_message` ; corriger (poste libre ? contexte valide ?), puis **Réessayer**.     |
| « déjà existe » (409) poste        | normal : l'extension est réutilisée (reprise idempotente).                                 |
| Suppartielle / ressource orpheline | relancer **Supprimer les ressources Wazo** (idempotent, 404 ignorés).                      |
| Softphone inactif                  | vérifier « voip » installé + `wazo.softphone_enabled` + URL WebSocket.                     |
| Double compte SIP à la resync      | ne doit pas se produire (409 → récupéré par username) ; sinon nettoyer via authd par UUID. |

### Commande de test (ci)

```bash
cd ~/hermes-dev/odoo20 && PYTHONPATH="" .venv/bin/python odoo/odoo-bin \
  -c conf/odoo.conf --database odoo20 -u wazo_phone \
  --test-tags wazo_phone --stop-after-init --log-level=test
```

Suite : 60 tests (access 7, cdr 13, client 12, user 8, voip_bridge 20).
