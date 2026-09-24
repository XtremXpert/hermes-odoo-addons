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

### `wazo_phone`
Connecteur **Wazo Platform** : création d'utilisateurs Wazo (ligne SIP, poste,
endpoint, messagerie vocale) depuis un contact Odoo, création de **groupes
d'appel** (membres ordonnés par priorité de sonnerie), **inventaire du
contexte** (rattachements, postes orphelins, correspondance avec les fiches
Odoo), journal d'appels (`wazo-call-logd`) et **softphone WebRTC** dans Odoo
(moteurs sip.js et SDK Wazo). Les **plages d'extensions** sont lues dans Wazo
(`contextnumbers`) au lieu d'être recopiées : un poste hors plage, d'un autre
type, ou déjà en service, est refusé **avant** toute écriture distante.
175 tests.

### `wazo_server`
Côté **exploitant du PBX** : création et encadrement des **tenants** Wazo.
Un tenant est créé de bout en bout — tenant (wazo-auth), **contexte interne et
plages d'extensions** (wazo-confd), **utilisateur administrateur** avec la
politique d'administration, **jeton d'API** à expiration longue — puis
**supprimé sous garde** : la suppression refuse tant qu'il porte des postes ou
des lignes, et énonce ce qui reste. Dépend de `wazo_phone` (client et réglages
partagés) ; un tenant installe `wazo_phone` seul et n'hérite jamais de cette
machinerie. 23 tests.

**Limite connue, mesurée** : le jeton d'un tenant **ne le cloisonne pas**. Un
jeton de tenant peut lire les données d'un autre tenant en changeant l'en-tête
`Wazo-Tenant` (les ACL de Wazo sont des chaînes indépendantes du tenant). La
frontière réelle se place à l'**URL** — un point d'entrée par tenant qui impose
l'en-tête —, pas dans le jeton. Détail et mesures : `doc/P5_WAZO_SERVER_SPEC.md`.

## Utilisation

1. Cloner le dépôt.
2. Ajouter le chemin à l'`addons_path` d'Odoo (ou copier chaque module).
3. Installer les modules :
   ```sh
   odoo-bin -d <db> -i mailcow_admin,voipms_sms,asterisk_ari,wazo_phone,wazo_server --stop-after-init
   ```
4. Configurer :
   - Réglages → **Mailcow** (URL + clé API)
   - Réglages → **SMS VoIP.ms** (utilisateur + token)
   - Réglages → **Téléphonie (Asterisk ARI)** (URL ARI + application + jeton)
   - Réglages → **Téléphonie Wazo** (URL du serveur, jeton API, tenant)
     — côté serveur, c'est le **jeton administrateur** du PBX ; côté tenant,
     c'est son **jeton de tenant**, fabriqué par `wazo_server`.
   
   Puis tester chaque connexion.

## Tests

```sh
odoo-bin -d t_test -i mailcow_admin,voipms_sms,asterisk_ari,wazo_phone,wazo_server \
  --test-tags=/mailcow_admin,/voipms_sms,/asterisk_ari,/wazo_phone,/wazo_server \
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

## Licence

**LGPL-3** — GNU Lesser General Public License, version 3 : voir [`LICENSE`](LICENSE).

C'est la licence déclarée par chacun des modules (`'license': 'LGPL-3'`) et
celle à laquelle renvoient les en-têtes de fichiers (« See LICENSE for
details »).

La LGPL-3 **incorpore les termes de la GPL-3** par référence, là où elle n'y
déroge pas : les deux textes sont donc versionnés ici — [`LICENSE`](LICENSE)
pour la LGPL-3, [`LICENSE.GPL-3`](LICENSE.GPL-3) pour la GPL-3 (GNU General
Public License, version 3, 29 juin 2007). Les textes sont repris tels quels de
<https://www.gnu.org/licenses/>.
