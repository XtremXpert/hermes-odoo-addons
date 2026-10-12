# Addons custom Odoo (Diverse-Cité)

[![CI](https://github.com/XtremXpert/hermes-odoo-addons/actions/workflows/ci.yml/badge.svg)](https://github.com/XtremXpert/hermes-odoo-addons/actions/workflows/ci.yml)
[![Pre-commit Status](https://github.com/XtremXpert/hermes-odoo-addons/actions/workflows/pre-commit.yml/badge.svg?branch=20.0)](https://github.com/XtremXpert/hermes-odoo-addons/actions/workflows/pre-commit.yml?query=branch%3A20.0)
[![Build Status](https://github.com/XtremXpert/hermes-odoo-addons/actions/workflows/test.yml/badge.svg?branch=20.0)](https://github.com/XtremXpert/hermes-odoo-addons/actions/workflows/test.yml?query=branch%3A20.0)

Dépôt au format des dépôts de modules de l'OCA (gabarit `oca-addons-repo-template`,
voir `.copier-answers.yml`) : chaque module est à la racine, avec son `pyproject.toml`,
son `readme/` et le `README.rst` qui en est généré ; `pre-commit` applique les contrôles
de l'OCA.

<!-- prettier-ignore-start -->

[//]: # (addons)

This part will be replaced when running the oca-gen-addons-table script from OCA/maintainer-tools.

[//]: # (end addons)

<!-- prettier-ignore-end -->

Des modules Odoo maison pour la série **20.0** (branche `20.0`) : les versions des modules
suivent la forme de l'OCA, `20.0.x.y.z`.

Les conventions du dépôt, les commandes de lancement, de test et de vérification, et les
pièges connus sont dans [`AGENTS.md`](AGENTS.md).

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
via son API REST v1 (`X-API-Key`).

### `voipms_sms`
Envoi de **SMS** via l'API **VoIP.ms** (REST v1, `api_username`/`api_token`) :
DIDs, boîte d'envoi segmentée (150 car., format `n/N`), réglages, droits.

### `asterisk_ari`
**Click-to-call** et suivi d'appels via l'**API ARI** d'Asterisk/FreePBX :
bouton « Appeler » sur la fiche partenaire, historique des appels
(état, ID ARI, erreurs), réglages + test de connexion.

### `wazo_phone`
Connecteur **Wazo Platform** : création d'utilisateurs Wazo (ligne SIP, poste,
endpoint, messagerie vocale) depuis un contact Odoo, création de **groupes
d'appel** (membres ordonnés par priorité de sonnerie), **inventaire du
contexte** (rattachements, postes orphelins, correspondance avec les fiches
Odoo), journal d'appels (`wazo-call-logd`) et **softphone WebRTC** dans Odoo
(moteurs sip.js et SDK Wazo). Les **plages d'extensions** sont lues dans Wazo
(`contextnumbers`) au lieu d'être recopiées : un poste hors plage, d'un autre
type, ou déjà en service, est refusé **avant** toute écriture distante.

### `hermes_n3_access`
Compte Odoo de l'agent d'infrastructure **Hermes N3** (`hermes_n3`, API JSON-2
seulement, jamais administrateur), désactivé avec ses clés API à la neutralisation
d'une copie de la base. Utilisé par diverse-odoo et mac-demo, qui le vendorisent.

### `hermes_n1_audit`, `hermes_activity`, `hermes_n1_website`, `hermes_dashboard_sso`
Socle commun des agents **Hermes**, vendorisé par maison (et à terme mac-demo) :
façade d'écriture de N1 avec journal immuable et provenance par message Discuss
(`hermes_n1_audit`), réponses et activité des agents dans Discuss (`hermes_activity`),
modification des pages du site dans la zone `#wrap` (`hermes_n1_website`), et
authentification OAuth2 + PKCE des tableaux de bord, Odoo fournisseur d'identité
(`hermes_dashboard_sso`). Les modules propres à une instance (`hermes_n2_support`,
`hermes_n3_infra`, `hermes_coordination`) restent dans maison.

### `wazo_server`
Côté **exploitant du PBX** : création et encadrement des **tenants** Wazo.
Un tenant est créé de bout en bout — tenant (wazo-auth), **contexte interne et
plages d'extensions** (wazo-confd), **utilisateur administrateur** avec la
politique d'administration, **jeton d'API** à expiration longue — puis
**supprimé sous garde** : la suppression refuse tant qu'il porte des postes ou
des lignes, et énonce ce qui reste. Une **fiche de remise** calcule le bloc à
copier pour l'exploitant du tenant (URL, jeton, tenant, contexte, administrateur,
expiration), étiqueté comme les réglages de `wazo_phone`. Dépend de `wazo_phone`
(client et réglages partagés) ; un tenant installe `wazo_phone` seul et
n'hérite jamais de cette machinerie. Sur l'instance de l'**exploitant**, chaque
poste et chaque groupe d'appel **choisit son tenant** — l'en-tête et le contexte
envoyés en découlent — et le voit en permanence : colonne de liste, filtre et
groupement. Un jeton qui a pu fuiter se **reprend** : « Renouveler le jeton » en
fabrique un neuf et révoque l'ancien, sans détruire le tenant ni ses postes. Un
Wazo **déjà peuplé** se rattrape par « **Adopter les tenants du PBX** » : la
liste est lue **à la racine** (le listage de wazo-auth est cloisonné — partir du
tenant des réglages ne montrerait que lui et ses enfants), chaque fiche arrive
avec son **contexte réel**, et les fiches déjà connues ne sont **jamais**
touchées. Les secrets, eux, ne reviennent pas : le PBX ne rend ni jeton ni mot
de passe d'administration — la fiche de remise les donne à ressaisir, et
« Renouveler le jeton » les régénère.

**Limite connue, mesurée** : le jeton d'un tenant **ne le cloisonne pas**. Un
jeton de tenant peut lire les données d'un autre tenant en changeant l'en-tête
`Wazo-Tenant` (les ACL de Wazo sont des chaînes indépendantes du tenant). La
frontière réelle se place à l'**URL** — un point d'entrée par tenant qui impose
l'en-tête —, pas dans le jeton. Détail et mesures : `doc/P5_WAZO_SERVER_SPEC.md`.

**Cloisonnement du listage, mesuré** : une liste de tenants ne montre que le
sous-arbre du tenant porté par l'en-tête `Wazo-Tenant`. Un **parent** est donc
hors d'atteinte avec l'en-tête de son enfant — `GET /tenants/<uuid>` répond
**404 « unknown-tenant »**, et non un refus de permission. L'adoption remonte
donc à la racine en interrogeant chaque tenant avec **son propre** en-tête. Le
tenant `master` de Wazo n'a, lui, **aucun contexte** : la fiche de remise
affiche « inconnu » plutôt que d'inventer un nom.

## Environnement de développement local

Le dépôt est fait pour **`odoo-dev`** (CLI Bemade, `uv tool install odoo-dev`),
en **venv Python natif** — Docker n'est qu'un repli.

```sh
git clone --recurse-submodules <url>    # .deploy est un sous-module : sans lui, il est vide
cd <dépôt>
cp .env.exemple .env                    # ODOO_VERSION=20.0, PYTHON_VERSION=3.12
odoo-dev setup --no-docker --yes        # clone odoo/ + design-themes, bâtit .venv et conf/
./start.sh                              # lancement — jamais odoo-bin à la main
./tools/test mailcow_admin              # tests d'un module, sur une base jetable
```

Sans accès au dépôt privé `enterprise`, ajouter `--community` à `setup`.

- **`.env` et `.venv/` sont ignorés par git** : ils ne se transmettent donc pas
  par le clone. C'est à ça que sert `.env.exemple`.
- **`ODOO_VERSION=20.0`** : la branche `20.0` d'Odoo, celle des modules (`master` est
  passée à la série 20.1). Vide, `odoo-dev` retomberait sur son défaut — 18.0 — donc
  sur une autre Odoo que celle des modules.
- **`.deploy/`** est le sous-module `XtremXpert/odoo-deploy` (branche `19.0`) :
  gabarits k8s, `Dockerfile`, `compose.yaml`, et l'`odoo.conf` **du chemin
  Docker**. Celui-ci n'est pas celui que lit `./start.sh` — qui prend
  `conf/odoo.conf` (socket Unix, port 2069). La CI GitHub ne récupère pas le
  sous-module, et n'en a pas besoin.

## Utilisation

1. Cloner le dépôt.
2. Ajouter **la racine du dépôt** à l'`addons_path` d'Odoo (ou copier chaque module) :
   comme dans un dépôt de l'OCA, les modules sont à la racine. Un projet peut aussi les
   vendoriser (`odoo-dev vendor add <module> --source …`), comme le fait maison.
3. Installer les modules :
   ```sh
   odoo-bin -d <db> -i mailcow_admin,voipms_sms,asterisk_ari,wazo_phone,wazo_server --stop-after-init
   ```
4. Inscrire les utilisateurs aux groupes du module. Les menus sont rangés
   derrière eux et l'administrateur n'y est **pas** d'office : sans cette
   inscription, ni « Téléphonie Wazo » ni « Serveur Wazo » n'apparaissent — les
   menus existent en base, mais ne sont pas servis au client.
   ```sh
   # Réglages → Utilisateurs → admin → Téléphonie Wazo, ou :
   odoo-bin shell -d <db>
   >>> env['res.users'].search([('login', '=', 'admin')]).write(
   ...     {'group_ids': [(4, env.ref('wazo_phone.group_wazo_manager').id)]})
   >>> env.cr.commit()
   ```
   Le groupe « Téléphonie Wazo : Gestionnaire » implique « Utilisateur » ;
   `wazo_server` ajoute son propre groupe pour le menu « Serveur Wazo ».
5. Configurer :
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

Suite complète des cinq modules : **387 tests**, 0 échec (2026-10-07, image Odoo 20.0).

Les tests **JavaScript** du softphone (`wazo_phone/static/tests/`) sont des tests
**Node**, sans navigateur, et se lancent à part. 86 tests : arbitrage
multi-onglets, choix du moteur SIP, bundle SDK. Les ignorer n'est pas neutre —
aucun test Python ne voit le JS.

```sh
node --test '*/static/tests/*.test.js'
```

## Notes

- **Rien ne charge le client web dans un navigateur.** Une erreur JavaScript
  (composant OWL, service, patch de vue) ne se voit ni dans les tests Python ni
  dans les tests Node : les tests ci-dessus ne couvrent que la logique sans
  navigateur. Après toute modification d'un fichier de `static/src/`, ouvrir
  `/odoo` — c'est la seule vérification qui attrape cette classe de faute.
  Et si le correctif semble sans effet, **lire les octets servis**, pas la
  source : un paquet d'actifs en cache peut survivre à `-u <module>`.
- **L'ordre dans le paquet d'actifs décide du démarrage du client.** Odoo
  assemble `web.assets_backend` en parcourant les modules **triés
  topologiquement**, les ex æquo gardant l'ordre des noms : `wazo_phone` passe
  donc **avant** `web` (« waz » < « web »). Sans ordre explicite, nos fichiers
  s'exécutent avant `module_loader.js`, qui définit `odoo.define` : le premier
  lève « odoo.define is not a function » et le client reste blanc, sans la
  moindre erreur côté serveur. D'où la commande
  `('after', 'web/static/src/module_loader.js', …)` du manifeste et le test
  `TestAssetDependencies`, qui exige aussi la dépendance `web`.
- **L'adresse d'un paquet d'actifs porte son empreinte** : redemander l'ancienne
  adresse ressert l'ancien contenu, et l'empreinte change aussi quand seul un
  manifeste change — une empreinte neuve ne prouve donc pas une reconstruction.
  Pour mesurer : purger les paquets en cache, ou demander l'adresse avec un
  segment fantaisiste et suivre la redirection. Vérifier qu'un **seul** serveur
  écoute (`lsof -ti:2069`) avant toute mesure : deux processus, et toutes les
  mesures mentent.
- **`ir.ui.menu.search_count` ne dit pas ce que l'utilisateur voit.** Un menu
  restreint à un groupe y compte comme visible alors que
  `/web/webclient/load_menus` — la charge utile dont le navigateur rend les
  menus — ne le contient pas. Vérifier la visibilité des menus uniquement sur
  cette charge utile.

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
