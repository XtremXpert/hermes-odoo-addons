# Spec P3 — Softphone Wazo, **voie native WebRTC** (v3 — 2026-09-24)

> Module **`wazo_phone`** — architecture cible du softphone navigateur. **v3 change de
> socle** : le navigateur parle **directement à Wazo** en SIP-over-WSS, sur un
> **endpoint WebRTC natif**. **Plus de relay, plus de B2BUA, plus de proxy média à
> écrire.** La v2 (relay Sippy B2BUA + RTPProxy) a été **techniquement validée** puis
> **abandonnée** : elle résolvait côté serveur un problème que Wazo règle nativement.
> Son historique est conservé en **Annexe A** (§1-§12) et **Annexe B** (§13-§16) — il
> reste la référence des pièges SIP rencontrés.

---

## Décision d'architecture — voie native (NORMATIF)

**Décidée et validée le 2026-09-24, en conditions réelles.**

### Le raisonnement (ce qui manquait à la v2)

La v2 posait comme objectif « **1 REGISTER par user, quel que soit le nombre d'onglets**
» et en déduisait qu'il fallait un **relay serveur**. Deux erreurs :

1. **Le problème multi-onglets est un problème _client_.** Le comptage des registrations
   n'était pas la vraie difficulté : ce qui casse, c'est que N onglets croient chacun
   être _le_ téléphone (sonnerie multiple, double décrochage, états divergents). Ça se
   règle **dans le navigateur** (arbitrage de propriété), pas en ajoutant un composant
   SIP serveur.
2. **Wazo sait déjà faire du WebRTC.** Le socle natif est là, par défaut : transport
   **`transport-wss`** chargé, **template SIP `webrtc` par tenant** dans confd
   (`webrtc_sip_template_uuid`), et `wss://<host>/api/asterisk/ws` servi par son nginx.
   Les endpoints `webrtc1001`/`webrtc1002` (ext 1001/1002) ont été créés **dès le début
   du projet** et portent déjà `opus`, `bundle: true`, `dtls_auto_generate_cert` sur
   `transport-wss`. → Le relay a donc été construit **par-dessus un chemin qui existait
   déjà**.

### Critère de décision (à appliquer à toute demande future)

Un relay est un **choix contraint**, jamais un défaut. Il ne se justifie que par une
**contrainte nommée** :

| Besoin                                             | Voie native (browser → Wazo)                 | Relay (B2BUA + pile média maintenue) |
| -------------------------------------------------- | -------------------------------------------- | ------------------------------------ |
| 1 user, N onglets                                  | **Oui** (arbitrage client)                   | Surdimensionné                       |
| Credentials jamais dans le navigateur              | Plus faible (tokens courts possibles)        | Oui                                  |
| Ligne enregistrée avec **tous** les clients fermés | Non (il faut un autre endpoint sur la ligne) | Oui                                  |
| Enregistrement / whisper / barge                   | Non                                          | Oui                                  |
| Interop SIP legacy non-WebRTC                      | Non                                          | Oui                                  |

Si aucune ligne de droite ne s'applique → **voie native, point**. Et si un relay devient
réellement nécessaire, il se construit sur une **pile média maintenue**
(Kamailio/OpenSIPS + rtpengine, Asterisk-en-B2BUA, Janus, LiveKit) — **jamais**
l'application de démonstration d'une bibliothèque de test SIP.

**Ne jamais justifier un relay par l'édition Odoo.** Community vs Enterprise est un fait
de **couche application** (pas de module `voip` → d'où le softphone maison) ; le choix
du substrat SIP/média lui est **orthogonal**.

### Preuve de validation

La démo officielle `wazo-webrtc-demo` (plugin Wazo, MIT), servie en HTTPS par le cert
Let's Encrypt de la VM : connexion, **appel établi et audio dans les deux sens**, **sans
aucun relay dans le chemin**. Recette de vérification reproductible (4 commandes) :
skill `wazo-operations` → `references/webrtc-native-path.md`.

### Architecture

```
   ┌──────────────────────  BROWSER (1..N onglets)  ───────────────────────┐
   │  Widget softphone DANS Discuss (OWL + SIP.js)                          │
   │  ├─ arbitrage de propriété (Web Locks + BroadcastChannel)              │
   │  ├─ leader : UserAgent SIP.js ── SIP/WSS ──► Wazo /api/asterisk/ws     │
   │  │            média : DTLS-SRTP + ICE, de bout en bout                 │
   │  └─ bus Odoo ─► notif d'appel, journal CDR, état (canal par user)      │
   └────────────┬────────────────────────────────────────┬─────────────────┘
                │ (a) SIP/WSS 443 : signaling + média     │ (b) /websocket
                ▼                                         ▼   (session Odoo)
   ┌───────────────────────────────────┐   ┌──────────────────────────────┐
   │ WAZO 26 (Asterisk pjsip)          │   │ ODOO (wazo_phone)            │
   │ - transport-wss (natif)           │   │ - sync confd (template webrtc)│
   │ - endpoint WebRTC par device      │   │ - mapping user↔ligne, CDR    │
   │   (template `webrtc` confd)       │   │ - bus : notif + état         │
   │ - lignes multi-endpoints (forking)│   └──────────────────────────────┘
   └───────────────────────────────────┘
```

### Composants

| Composant             | Rôle                                                                     | Stack                              | Licence      |
| --------------------- | ------------------------------------------------------------------------ | ---------------------------------- | ------------ |
| **Wazo 26**           | registrar + **endpoint WebRTC** + terminaison média                      | pjsip `transport-wss`              | —            |
| **Widget Discuss**    | UI softphone + client SIP                                                | OWL/JS + SIP.js **ou** `@wazo/sdk` | LGPL-3 + MIT |
| **Odoo `wazo_phone`** | sync confd (template `webrtc`), mapping user↔ligne, CDR (call-logd), bus | Python (Odoo 20)                   | LGPL-3       |

_(plus de composant relay.)_

### Moteur SIP : SDK officiel Wazo retenu (décision P3.3f)

Deux moteurs étaient possibles : **SIP.js écrit à la main** (notre P3.3a/b) ou le
**`WebRTCClient` du SDK officiel**. Décision : **le SDK**, sur faits relevés dans
l'artefact `@wazo/sdk` 0.49.5 — pas sur préférence.

| Fait vérifié                                                                                    | Conséquence                                                                                                                                                      |
| ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Le SDK dépend de **`sip.js@^0.21.2`** — la version exacte que nous vendorisons                  | Ce n'est pas un fork : **la pile SIP ne change pas**                                                                                                             |
| Il publie `dist/wazo-sdk.js` : **UMD, dépendances inlinées**                                    | Vendorisable **sans étape de build** (l'objection « 8 polyfills webpack » ne concerne que la source, pas cet artefact)                                           |
| Il construit l'URL WS lui-même : `wss://<hôte>:<port>/api/asterisk/ws`                          | Il faut lui passer **hôte + port**. Lui donner une URL complète le casse : il découpe `websocketSip` sur `:` et prendrait `wss` pour un hôte, `NaN` pour un port |
| Il dérive l'URI/From de `authorizationUser` (`sip:<user>@<hôte>`)                               | Ce champ doit porter **l'AOR (nom d'endpoint)**, pas l'extension — le piège P3.2 remonte à la surface                                                            |
| `CONNECTED`/`DISCONNECTED` sont des événements de **transport** ; l'appel établi est `ACCEPTED` | Ne pas confondre : le transport ouvert n'est pas une conversation                                                                                                |
| `sendDTMF` prend **une seule touche**                                                           | Une séquence doit être bouclée touche par touche                                                                                                                 |
| Ses noms d'exports (66) sont étalés sur la racine par le repli UMD                              | **Enveloppé dans une IIFE** → exposé sous `window.WazoSDK` uniquement                                                                                            |

**Ce qui a emporté la décision** : le chemin SIP.js écrit à la main ne câblait **aucun
élément audio distant** — il se connectait, mais restait **muet**. Le SDK fournit
précisément ce que nous aurions dû réécrire et mal écrire : attachement du média distant
(`ON_TRACK`), détection d'IP privée pour l'ICE, heartbeat de transport, reconnexion ICE,
statistiques réseau, et gestion conference/vidéo dans hold et transfert.

**État** : bundle vendorisé (`tools/vendor_wazo_sdk.sh`, enveloppe incluse), bundle
`wazo_phone.assets_sdk` **lazy-loadé** (1,7 Mo minifié, coût nul tant que le moteur
n'est pas sélectionné), **moteur interchangeable** livré : le service ne parle plus à
SIP.js en direct, il reçoit un moteur (`wazo_softphone_engine.esm.js`) dont le choix
vient de `wazo.softphone_engine` — donc d'un paramètre, pas d'un redéploiement — et
chaque moteur est testé isolément hors navigateur (67 tests Node : traduction de
configuration, tables d'événements, découpage DTMF, tolérance sans session, sélection).
Reste la **QA navigateur** : elle seule dira si la conversation passe, et c'est elle qui
tranchera sur pièce.

### Flows

- **Registration** — 1 client SIP par **device** (l'onglet leader), endpoint construit
  sur le template `webrtc` du tenant, vers `wss://<host>/api/asterisk/ws`. Le
  multi-device se fait par **plusieurs endpoints sur une même `line`** (Wazo fork
  nativement) — jamais par des contacts multiples sur un AOR.
- **Appel entrant** — Wazo forke vers les contacts de la ligne → le leader reçoit
  l'INVITE → **diffusion `incoming`** aux onglets attachés (via le bus) → le **premier
  `answer` gagne** → `claimed{tabId}` aux autres, qui passent en **télécommande** (hold
  / DTMF / transfert / raccrocher restent opérants : l'appel appartient à la session,
  pas à l'onglet).
- **Appel sortant** — le leader INVITE directement Wazo ; les autres onglets reflètent
  l'état via le bus.
- **Hold / transfert / DTMF** — primitives SIP.js (`hold()`/`unhold()` RFC 6337,
  `refer()` RFC 3515, `sendDtmf()`) **ou** l'implémentation `WebRTCClient` du SDK
  officiel, qui a déjà payé les bugs de rollback de re-INVITE.

### Multi-onglets & multi-device

**Deux propriétés distinctes, à ne pas confondre :**

| Propriété            | Objet                       | Mécanisme                         |
| -------------------- | --------------------------- | --------------------------------- |
| **de la couche SIP** | qui enregistre (1 REGISTER) | verrou exclusif `navigator.locks` |
| **de l'appel**       | qui a décroché              | revendication `claimed` diffusée  |

Un onglet peut détenir la couche SIP **sans** être maître de l'appel : c'est le cas
normal quand un autre onglet décroche. Les autres sont alors des **télécommandes** —
leurs commandes (hold, DTMF, transfert, raccrocher) remontent au propriétaire, qui les
exécute sur la session.

- **Élection** : `navigator.locks.request(verrou, {mode: "exclusive"}, cb)`. Le verrou
  se libère à la fermeture de l'onglet → **le suivant le prend** ; `onLeadership(true)`
  le prévient pour qu'il démarre _sa_ couche SIP. Sans cette reprise, fermer un onglet
  rendrait le téléphone muet.
- **Canal** : `BroadcastChannel` (messages `leader`, `claim`, `release`, `incoming`,
  `state`, `command`, `detach`). Un message illisible ou étranger est **ignoré** : la
  perte d'un message d'arbitrage ne casse jamais un appel.
- **Course au décroché** : deux onglets peuvent cliquer « répondre » au même instant.
  Départage **déterministe par identifiant d'onglet** (le plus petit gagne), pour que
  tous les onglets désignent le même gagnant — sinon l'appel serait répondu deux fois.
- **Fin d'appel** : `release` libère la revendication et clôt l'appel entrant partout.
- **Survie** : leader fermé, l'appel en cours **survit** (il vit dans la session SIP et
  chez Wazo, pas dans l'onglet) ; l'appel entrant en cours est conservé par le
  successeur.
- **Repli** : sans Web Locks (contexte non sécurisé), l'onglet se comporte comme seul au
  monde — le softphone marche, seul l'arbitrage est perdu.
- **Devices** : **lignes Wazo multi-endpoints**. Jamais `MaxContact` > N par AOR. Le
  nombre d'onglets n'a plus d'effet sur Wazo : **un** endpoint enregistré par device,
  quel que soit le nombre d'onglets.

**Vérification** : la logique d'arbitrage est un module isolé
(`wazo_softphone_arbiter.esm.js`), avec les adaptateurs (verrou, canal) **injectés**
pour être testable hors navigateur —
`node --test static/tests/wazo_softphone_arbiter.test.js` (16 tests : élection, reprise,
course au décroché, télécommande, tolérance aux messages invalides).

### Auth & sécurité

- Le navigateur porte les credentials de **son** endpoint (assemblés côté Odoo) ;
  variante durcie : tokens courts — le SDK s'authentifie auprès de wazo-auth et récupère
  lui-même les creds de l'endpoint.
- Le bus Odoo reste la couche **app** (notif, CDR, état) — **jamais** le transport SIP.
- Aucun secret en clair en base (`ir.config_parameter` / `res.config.settings`).

### Scaling & limites

- `maxwebsocketclients` (`/etc/asterisk/http.conf`, défaut Asterisk **10**) : avec
  l'arbitrage il y a **1 WSS par user+device**, donc le mur ne se pose plus. À relever
  uniquement si l'arbitrage est abandonné.
- Pas de TURN en général ; utile seulement derrière un NAT symétrique.

### Modes de défaillance

| Défaillance             | Comportement                                                                                                     |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Onglet leader fermé     | Le suivant prend le verrou et se ré-enregistre ; l'appel en cours survit                                         |
| Tous les onglets fermés | Plus d'endpoint enregistré → Wazo route selon son forward/boîte vocale (limite native — cf. tableau de décision) |
| Bus Odoo coupé          | L'appel **continue** (SIP + média indépendants du bus) ; seuls notif/état sont perturbés                         |
| User sur 2 devices      | 2 endpoints, forking Wazo natif                                                                                  |

### Intégration Odoo Discuss (+ bonus Community)

Inchangé sur le fond : l'UI vit dans **Discuss** (Community **et** Enterprise), les
appels surgissent en **notifications Discuss**, l'intégration applicative passe par le
**bus** (canal par user : notif, journal CDR, état multi-onglets). Le softphone n'est
**conditionné à aucune édition** — il n'utilise ni le module `voip` (Enterprise) ni un
relay ; le pont `voip_bridge` reste un no-op optionnel.

### Phasage

| Phase                   | Livrable                                                                                | État                                                                                                        |
| ----------------------- | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **P3.0**                | `maxwebsocketclients` relevé + endpoint `webrtc` validé                                 | endpoint **validé par la démo** ; réglage `http.conf` à confirmer                                           |
| **P3.1 / P3.1b / P3.2** | relay Sippy (registrar, SIP-over-WSS, multi-user)                                       | **fait, validé, puis abandonné** (Annexe B) — reste la référence des pièges SIP                             |
| **P3.3a / P3.3b**       | backend softphone + UI Discuss (hold/transfert/DTMF + journal CDR)                      | **complet, 84/84 tests** — **conservé tel quel**                                                            |
| **P3.3c**               | `softphone.py` : `_softphone_ws_url()` → `wazo.ws_url` ; `wazo.softphone_ws_url` retiré | ✅ fait — 89/89 tests                                                                                       |
| **P3.3d**               | sync confd : endpoint référant les templates **`global` + `webrtc`** du tenant          | ✅ fait — payload identique à `webrtc1001` (vérifié live)                                                   |
| **P3.3e**               | arbitrage multi-onglets (Web Locks + `claimed`) + télécommande                          | ✅ fait — 16/16 tests Node, bundle +7 336 o                                                                 |
| **P3.3f**               | décision **SDK `@wazo/sdk`** vs SIP.js + portage hold/transfert                         | ✅ **fait** — SDK retenu, bundle vendorisé, moteur interchangeable (`wazo.softphone_engine`), service câblé |
| **P3.3g**               | notifications d'appel entrant par le **bus Odoo** (canal par utilisateur)               | à faire                                                                                                     |
| **P3.4**                | démontage : B2BUA, `wazo_registrar.py`, `run_b2bua.sh`, proxy nginx `b2bua…` + son cert | à faire                                                                                                     |

### Décisions (v3 — remplace le §12 de l'Annexe A)

1. **Socle = voie native.** Browser → Wazo en SIP-over-WSS, endpoint `webrtc`. Pas de
   relay. _(2026-09-24, validé avec audio.)_
2. **Multi-onglets = arbitrage client** (Web Locks + claim). Pas de consolidation
   serveur, pas de contacts multiples par AOR.
3. **Multi-device = lignes Wazo** multi-endpoints.
4. **Community non contraignant** : l'édition n'entre pas dans le choix du substrat.
5. **Relay** : uniquement sur contrainte nommée (tableau de décision).
6. **`voip_bridge`** conservé en no-op optionnel (compat Enterprise), jamais requis.

---

## Annexe A — design v2 « relay Sippy » (HISTORIQUE, non normatif)

> Les **§0 à §12** ci-dessous décrivent le design **v2** (relay B2BUA + RTPProxy greffé
> sur le PoC `sippy/webrtc_phone`). Ils sont **conservés comme historique** : la v2 a
> été techniquement validée (§13-§16) puis **abandonnée** au profit de la **voie
> native** (section NORMATIF en tête de document). **Ne pas les lire comme la cible.**

## 0. Antécédent — ce qui existe déjà sur GitHub

**[`sippy/webrtc_phone`](https://github.com/sippy/webrtc_phone)** (Vonage, Docker, actif
— dernier commit mai 2025) **est l'architecture P3** : client WebRTC (SIP.js) →
**B2BUA** → SIP → PBX. 4 composants :

1. **Sippy B2BUA** (Python) — B2BUA RFC3261 carrier-grade, en production chez Vonage.
2. **Sippy RTPProxy** (C) — proxy de **média** RTP (NAT-safe).
3. App de démo **SIP.js** (navigateur).
4. Serveur web statique (sans rôle dans la session).

Fonctionnement (README) : le navigateur fait **SIP/WSS vers le B2BUA** ; le B2BUA
**proxie l'enregistrement** vers le registrar SIP externe (Wazo) via SIP/UDP ; à
l'appel, B2BUA+RTPProxy montent 2 sessions RTP (chiffrée + plain) et lancent l'appel.
**Perf revendiquée : ~500 users concurrents / container (5–6 cœurs).**

**Licence** : Sippy B2BUA = « la licence open source la plus libérale qui soit » (PyPI)
→ **MIT**, compatible LGPL d'Odoo. RTPProxy = open source (sippy/rtpproxy).

**Ce qui n'existe PAS (notre delta)** : aucun projet ne fait **1 registration par user
en Wazo + fan-out « ring-all » vers N onglets** du même user **intégré à une app métier
(Odoo)** (bus + widget Discuss). Le démo Sippy est **1:1**. La **consolidation
multi-onglets sur une seule registration** + **l'intégration Odoo** = la part nouvelle,
posée sur des briques prouvées.

## 1. Problème

Le pont actuel (route A, module `voip` Enterprise) crée **1 socket WSS + 1 REGISTER par
onglet** pour la même identité SIP. Sur la VM : `maxwebsocketclients` = **10** (par
défaut Asterisk) → mur atteint sous charge (`nb_onglets × nb_users`). La redondance
inter-device (portable + laptop) est un **avantage** qu'on conserve ; seule la
redondance **intra-device** (les onglets) doit disparaître.

## 2. Principe

Un **relay** = **Sippy B2BUA (Python) + Sippy RTPProxy (C)**, en **sidecar** (processus
dédié, pas un worker Odoo) :

- **Jambe navigateur** : le navigateur exécute **SIP.js** et fait **SIP/WSS vers le
  B2BUA** (port 9876). C'est le B2BUA qui absorbe les N sockets par-onglet — Wazo ne les
  voit pas.
- **Jambe Wazo (A)** : le B2BUA tient **1 registration SIP par user** vers le registrar
  Wazo (SIP/UDP 5060). **C'est le cœur de P3** : le B2BUA est configuré pour
  **consolider** les sessions navigateur d'un user sur **une seule registration Wazo**
  et faire **ring-all** vers tous ses onglets.
- **Média** : **proxifié par RTPProxy** (navigateur ↔ RTPProxy ↔ Wazo). **NAT-safe** —
  pas de P2P ICE à forcer (risque v1 absorbé).
- **Odoo** : hôte de l'UI (widget Discuss), auth (credentials SIP), mapping user↔ligne,
  CDR, notifications d'appel + coordination multi-onglets **via le bus WebSocket
  `/websocket`**.

Conséquence : le nombre d'onglets **n'a plus d'impact** sur les connexions SIP Wazo. 1
user = 1 REGISTER Wazo, que tu aies 1 ou 20 onglets.

## 3. Architecture

```
   ┌──────────────────────────  BROWSER (1..N onglets)  ──────────────────────────┐
   │  Widget softphone DANS Discuss (OWL + SIP.js) : pavé, statut, Répondre/Refuser│
   │  ├─ SIP.js ──► SIP/WSS (signaling + registration)                            │
   │  └─ bus Odoo ─► notif appel, CDR, coordination multi-onglets (canal par user)│
   └───────────▲───────────────────────────────────────────────┬───────────────────┘
               │ (a) SIP/WSS 9876/TCP                           │ (b) WebSocket /websocket
               │                                                │   (auth session Odoo)
   ┌───────────┴────────────────────────────────────────────────┴───────────────────┐
   │  RELAY (sidecar dédié — SIPPY)                                                 │
   │  ┌──────────────────────────────┐   ┌───────────────────────────────────────┐  │
   │  │ Sippy B2BUA (Python)          │   │ Sippy RTPProxy (C)                    │  │
   │  │ - WSS 9876 (N sockets onglets)│   │ - proxy média RTP (NAT-safe)          │  │
   │  │ - CONSOLIDE 1 registration/   │   │ - navigateur ↔ RTPProxy ↔ Wazo        │  │
   │  │   user vers Wazo (cœur P3)    │   └───────────────────────────────────────┘  │
   │  │ - ring-all vers N onglets, DTMF│                                                │
   │  │ - appel sortant, hold, BYE    │                                                 │
   │  └──────────────┬────────────────┘                                                │
   └─────────────────┼─────────────────────────────────────────────────────────────────┘
                     │ (A) SIP/UDP 5060 — 1 REGISTER/user   +    (M) RTP proxifié
             ┌───────▼────────────────────────────────┐
             │   WAZO 26  (Asterisk pjsip)            │
             │ registrar 0.0.0.0:5060/udp, media RTP  │
             └────────────────────────────────────────┘

   Odoo (wazo_phone) — hors chemin média :
   - widget Discuss (hôte UI), auth/credentials SIP, mapping user↔ligne, CDR,
     notifications appel + coordination multi-onglets via le bus /websocket.
```

## 4. Composants

| Composant             | Rôle                                                          | Stack                    | Licence              |
| --------------------- | ------------------------------------------------------------- | ------------------------ | -------------------- |
| **Relay — B2BUA**     | WSS (N onglets), **1 registration/user Wazo**, ring-all, DTMF | **Sippy B2BUA (Python)** | **MIT** — compatible |
| **Relay — média**     | proxy RTP NAT-safe                                            | **Sippy RTPProxy (C)**   | open source          |
| **Widget Discuss**    | UI softphone (pavé, statut, actions) + **SIP.js**             | OWL/JS + SIP.js (MIT)    | LGPL-3 + MIT         |
| **Odoo `wazo_phone`** | auth, mapping user↔ligne, CDR, bus (notif/coordination)       | Python (Odoo 20)         | LGPL-3               |
| **Wazo 26**           | registrar SIP + terminaison                                   | —                        | —                    |

> Le relay est un **processus dédié séparé** → pas de mélange de licence dans le module
> LGPL, et un bug relay ne fait pas tomber Odoo. Sippy = MIT, SIP.js = MIT.

## 5. Flows

### 5.1 Registration (le cœur de P3)

1. L'onglet (SIP.js) fait **REGISTER au B2BUA** (SIP/WSS 9876) avec l'identité du user
   (credentials issus d'Odoo).
2. Le B2BUA **consolide** : quel que soit le nombre d'onglets du user, il tient **1
   REGISTER vers Wazo** (1 contact Wazo par user).
3. Wazo voit **1 contact** (vs `nb_onglets` en route A). `maxwebsocketclients` n'est
   plus le goulot.

### 5.2 Appel entrant

1. Wazo envoie **INVITE** au contact (1 seul) du user.
2. Le B2BUA reçoit l'INVITE, crée une session, et le fait **sonner sur tous les
   onglets** du user (ring-all) via SIP.js.
3. Odoo, en parallèle, pousse une **notification bus** (« appel entrant de X ») → banner
   Discuss + widget.
4. L'onglet qui répond : SIP.js envoie le **200 OK** au B2BUA.
5. **Média établi via RTPProxy** (navigateur ↔ RTPProxy ↔ Wazo), NAT-safe.
6. Fin : `BYE`, B2BUA clôture, Odoo écrit la ligne CDR (call-logd).

### 5.3 Appel sortant

1. L'onglet (SIP.js) lance l'INVITE **au B2BUA** (numéro cible).
2. Le B2BUA route vers Wazo (`OUTBOUND_ROUTE`), sonnerie/établissement propagés.

### 5.4 Transfert / hold / DTMF

- Le B2BUA proxie les **re-INVITE** (hold/transfer), le **DTMF** et le **BYE**.
- Changer d'onglet = changer l'affichage ; la registration Wazo **ne bouge pas**.

## 6. Consolidation des registrations

|                                | Avant (route A)         | Après (P3)                           |
| ------------------------------ | ----------------------- | ------------------------------------ |
| Sockets WSS Wazo               | `nb_onglets × nb_users` | **≈ 0** (WSS absorbé par le B2BUA)   |
| REGISTER contacts Wazo         | 1 par onglet            | **1 par user**                       |
| Mur `maxwebsocketclients=10`   | atteint vite            | **inopérant**                        |
| Goulot                         | Wazo WSS                | **B2BUA** (~500 users/container)     |
| Multi-device (portable+laptop) | OK                      | **conservé** (1 REGISTER per device) |

## 7. Authentification & sécurité

- **Navigateur → B2BUA** : auth SIP (identifiant/secret user) ; le B2BUA n'accepte que
  les clients connus (listes IP/certificat, `--accept_ips`).
- **B2BUA → Wazo** : auth SIP par user (`OutboundAuth`), credentials générés par
  `wazo_phone` (pas en clair en base).
- **Navigateur → Odoo** : session Odoo (bus + widget). Le widget ne voit que le canal du
  **user connecté**.
- **Média** : SRTP/DTLS navigateur↔RTPProxy, puis RTPProxy↔Wazo (chiffré/plain selon
  config). Le chemin média est **isolé** du bus Odoo.

## 8. Scaling & limites

- Le goulot passe de « sockets WSS Wazo » à **la capacité du B2BUA** (~500 users /
  container, 5–6 cœurs). Scaling horizontal : plusieurs instances relay, répartition
  user↔instance **sticky** (`hash(uid) % N`).
- **RTPProxy** : chaque session alloue ~4 ports UDP ; dimensionner la plage
  (`MIN_RTP_PORT`/`MAX_RTP_PORT`) ≥ `max_sessions × 4`. `--network=host` recommandé.
- Pas de TURN nécessaire a priori (RTPProxy = médiateur média) ; optionnel en renfort.

## 9. Modes de défaillance

| Défaillance        | Comportement                                                                                                                      |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| Onglet ferme       | Les autres onglets du user restent joignables ; la registration Wazo **ne bouge pas**.                                            |
| Relay meurt        | La registration Wazo expire → user injoignable jusqu'au redémarrage. **watchdog + restart** (systemd) ; l'état se re-sync.        |
| Bus Odoo coupé     | L'appel en cours **continue** (SIP + média indépendants du bus) ; seule la notification/coordination est perturbée (re-sync bus). |
| User sur 2 devices | 2 registrations (1 par device), **ring-all** conservé.                                                                            |

## 10. Intégration Odoo Discuss — **oui, et c'est le meilleur port d'entrée**

Le softphone s'insère dans Discuss :

1. **UI** : le widget (pavé, statut, Répondre/Refuser/Transferer, DTMF) **vit dans
   Discuss** et **embarque SIP.js** (qui parle au B2BUA). Exactement le pattern
   `hermes_boutons` (patch OWL). Les appels **surgissent en notifications Discuss**
   (banner « Appel entrant de +1 555… — Répondre / Refuser »).
2. **Intégration applicative via le bus** (`/websocket`, `ir.websocket`,
   `subscribe(channels, last)`, notif + historique + rate-limit, auth session) : le
   widget se subscribe au **canal par user** pour (a) notifications d'appel, (b) journal
   CDR, (c) **coordination multi-onglets** (quel onglet est actif). → On **réutilise
   l'infra WebSocket existante d'Odoo** pour la couche app, sans en créer une nouvelle.

> **Précision v2** : le **transport SIP** (signaling + registration) va **navigateur →
> B2BUA** (SIP/WSS), **pas** par le bus. Le bus est la couche **app** (auth, CDR,
> notifications, coordination). Séparation plus propre que la v1.

### Bonus décisif : **compatibilité Community**

- L'UI est dans **Discuss** (Community + Enterprise), le transport SIP est notre
  **B2BUA + SIP.js** (pas le module `voip` Enterprise). → Le softphone P3 **n'est plus
  conditionné à Enterprise** : **Community ET Enterprise**.
- Le pont route A (Enterprise-only) devient **optionnel** (mode dégradé/legacy).

### Surfaces à ajouter dans `wazo_phone`

- **Auth/credentials** SIP par user + config du B2BUA (consolidation par user).
- **Endpoint interne** relay→Odoo (token service) pour les événements d'appel → publish
  **bus** (notification + CDR) et récupération des actions d'UI.
- Le **widget OWL Discuss** (assets + patch, pattern `hermes_boutons`) embarquant
  **SIP.js**.
- **CDR** (call-logd) déjà en place dans le module.

## 11. Complexité & phasage

| Phase      | Livrable                                                                                                              | Effort              | Risque                                              |
| ---------- | --------------------------------------------------------------------------------------------------------------------- | ------------------- | --------------------------------------------------- |
| **P3.0**   | Lever `maxwebsocketclients` + fixer payload (transport `wss` + `MaxContact`) → route A exploitable **dès maintenant** | faible              | faible                                              |
| **P3.0.5** | **PoC : tir du démo `sippy/webrtc_phone` (Docker) face à Wazo** — valider WebRTC traversant Wazo **avant** d'écrire   | faible              | config démo (identité Wazo, `OUTBOUND_PROXY/ROUTE`) |
| **P3.1**   | **Consolidation** : B2BUA = **1 registration/user** + **ring-all N onglets** (le delta P3, sur Sippy)                 | **le vrai morceau** | logique de consolidation + multi-onglets            |
| **P3.2**   | Appel sortant, hold/transfer, DTMF, fin, CDR branché                                                                  | moyen               | état re-INVITE                                      |
| **P3.3**   | Widget Discuss complet (SIP.js) + notifications + états + multi-device                                                | moyen               | UX                                                  |
| **P3.4**   | Hardening : watchdog relay, scaling horizontal, monitoring, auth durcie                                               | variable            | ops                                                 |

> **v2 — le risque technique n°1 de la v1 (ICE P2P / proxy SDP transparent) est ABSORBE
> par RTPProxy** (média proxifié, NAT-safe). Le vrai morceau d'effort passe à **P3.1 :
> la consolidation 1-registration/user + ring-all**, qui est le delta qu'aucun projet
> existant ne fournit.

## 12. Décisions

1. **Relay : sidecar dédié — DÉCIDÉ. Engine = Sippy B2BUA (Python) + RTPProxy (C) —
   DÉCIDÉ (v2).** Pas dans un worker Odoo (N workers parallèles Threaded/ Gevent/Prefork
   `os.fork()` **recyclés** `limit_time_worker_cron` → 1 registration persistante/user
   serait multipliée puis coupée ; Odoo isole déjà le bus WebSocket dans un processus
   longpolling dédié pour la même raison). **Correction v2** : Sippy B2BUA est un stack
   SIP **Python carrier-grade** (Vonage, RFC3261) → le relay **Python est légitime et
   préféré** (même langage que la partie Odoo), contrairement à l'intuition « SIP Python
   immature » de la v1 (qui visait pjsip, pas Sippy). Découpage : moteur SIP (B2BUA +
   RTPProxy) = sidecar ; auth, mapping, CDR, bus, widget OWL Discuss = Odoo.
2. **Routage user↔relay** : `hash(uid)%N` sticky (reco) vs table explicite.
3. **TURN** : optionnel (RTPProxy déjà médiateur média) — hors périmètre initial.
4. **Coexistence route A** : on garde le pont Enterprise comme mode dégradé, ou on
   bascule tout sur P3 (reco : coexistence, toggle par réglage).
5. **Canal bus exact** : à confirmer le nom de canal par user à l'implémentation
   (`_bus_channels()` du widget).
6. **P3.0.5 d'abord** : **oui** — tirer le démo Sippy face à Wazo (preuve que WebRTC
   traverse Wazo) **avant** d'écrire la consolidation.

## Annexe B — PoC & phases relay (HISTORIQUE VALIDÉ, non normatif)

> **§13 à §16** : résultats du chemin relay (PoC B.1, P3.1, P3.1b, P3.2, puis l'état
> P3.3). **Validé techniquement, abandonné architecturalement** (voir la section
> NORMATIF en tête). Ces sections restent la **référence des pièges SIP** rencontrés —
> identification d'endpoint, digest MD5/HA1, nom d'AOR ≠ extension, purge de cache
> confgen, hook cert Let's Encrypt. Ils sont également consolidés dans le skill
> `wazo-operations`.

## 13. PoC B.1 — Résultat validé (2026-09-23)

**Preuve obtenue** : REGISTER SIP **UDP direct** vers un endpoint custom Wazo → **200
OK + contact enregistré** dans l'AOR. Chaîne complète reproduite et diagnostiquée au
niveau source (Asterisk 22 / Wazo 26).

**Trois causes racine du 401/404, toutes corrigées (preuve source) :**

1. **Identification (le vrai 401)** — `res_pjsip_endpoint_identifier_user.c` :
   l'identification par username est **automatique** (`username_identify`), mais
   `find_endpoint` cherche un endpoint **nommé `<username>`** (fallback sans domaine).
   Les endpoints Wazo ont un **nom aléatoire** (`zj8xqf24`) et **aucune section
   `identify`** (confgen : `identify` = trunks uniquement, `_write_simple_endpoint` sans
   identify) → `Endpoint not found` → _artificial endpoint_ → FAIL. **Fix** : nommer
   l'endpoint custom **`<exten>`** (= username SIP).
2. **Mot de passe (MD5)** — Asterisk 22 exige `password_digest` (HA1) pour l'algo MD5 ;
   Wazo n'injecte que `password=` en clair (ignoré pour MD5). **Fix** :
   `password_digest=MD5:<HA1>` où `HA1 = MD5(user:realm:password)`.
3. **Registrar (le 404)** — `res_pjsip_registrar.c` / `find_registrar_aor` : l'AOR est
   résolu par match du **To URI** (`username@domain`) contre les **noms d'AOR** de
   l'endpoint. Un AOR nommé `<exten>-aor` ne matche ni `exten@domain` ni `exten`.
   **Fix** : nommer l'AOR **`<exten>@<domain>`**.

**Config endpoint custom qui marche (fichier `pjsip.d/`, reload à chaud) :**

```
[<exten>]            type=endpoint   aors=<exten>@<domain>  auth=<exten>-auth
[<exten>-auth]       type=auth       password_digest=MD5:<HA1>
[<exten>@<domain>]   type=aor        max_contacts=10
[<domain>]           type=domain     aors=<exten>@<domain>
```

avec `<domain>` = `asterisk` (default_realm Wazo). Digest client =
`MD5(HA1:nonce:nc:cnonce:auth:HA2)`, HA2 = `MD5(REGISTER:sip:<domain>)`, R-URI =
`sip:<domain>`.

**Implication produit (P3.1) :** un endpoint Wazo standard **ne s'enregistre jamais en
UDP** (pas d'identify + password en clair). Deux routes :

- **A — WSS bridge Wazo** (8089) : natif, mais **1 registration/onglet** (mur
  `maxwebsocketclients=10`) = le problème à résoudre.
- **B — endpoint custom + B2BUA** : B2BUA fait **1 REGISTER UDP/user** vers un endpoint
  custom (nommé par exten, AOR `exten@domain`, password_digest) ; N onglets du
  navigateur se connectent au **WSS de B2BUA** (port 9876, illimité, hors du
  maxwebsocketclients Asterisk). **Route B = validée par ce PoC.** C'est le delta
  produit.

### 13.3 Relay INVITE via B2BUA (vol 2) — validé

L'INVITE envoyé depuis le client UDP test (127.0.0.1:5171) vers B2BUA (5160) est
**re-émis par B2BUA** vers Wazo avec un `To;tag` généré :

```
INVITE sip:1005@asterisk SIP/2.0          ← reçu sur 5160
To: <sip:1005@asterisk>;tag=3ccc6b54...   ← B2BUA re-émet (proxy stateful)
```

C'est le comportement d'un proxy B2BU : il reçoit sur 5160, ré-échappe `Record-Route` +
`To;tag`, et relaye vers `static_route` (127.0.0.1:5060 = Asterisk). La boucle **client
→ B2BUA → Wazo → réponse** est ouverte.

**État B2BUA** : `--accept_ips=127.0.0.1:5171,[[WSS]],[[PROXY]]`,
`--static_route=127.0.0.1:5060`, `--sip_proxy=127.0.0.1:5060`, `--sip_port=5160`,
`--wss_socket=0.0.0.0:9876:cert:key` (TLS).

### 13.4 Fan-out N onglets sur le WSS B2BUA (vol 3) — validé

Deux clients WSS se connectent **simultanément** au port 9876 du B2BUA :

```
onglet-A: CONNECTE
onglet-B: CONNECTE
Résultat: 2/2 connectés  ✅
```

Le WSS du B2BUA accepte N connexions indépendamment du `maxwebsocketclients` Asterisk
(10 par défaut) qui plafonne la route WSS native Wazo (8089). **C'est la preuve du delta
: 1 REGISTER SIP/user (vers l'endpoint custom 5100) + N onglets navigateur via le WSS
B2BUA.**

### 13.5 Bilan du PoC B.1

| Vol                               | Preuve                       | Résultat                    |
| --------------------------------- | ---------------------------- | --------------------------- |
| 1. REGISTER UDP → endpoint custom | `test_register_udp.py`       | ✅ 200 OK + contact NonQual |
| 2. Relay INVITE via B2BUA         | `test_invite.py` (log B2BUA) | ✅ re-émis avec To;tag      |
| 3. Fan-out N onglets WSS B2BUA    | `test_fanout.py` (2 clients) | ✅ 2/2 connectés            |

Les 3 vols sont démontrés. Le delta produit (1 registration/user, N onglets) repose sur
la **route B** : endpoint custom nommé par extension

- B2BUA en relais. **P3.1 (consolidation B2BUA — 1 `SipRegistrationAgent` par user) est
  validé : voir §14.**

## 14. P3.1 — Registrar persistant `SipRegistrationAgent` (validé)

**Objectif** : remplacer le client de test brut par le mécanisme production Sippy — **1
`SipRegistrationAgent` par user**, dans un process dédié (`wazo_registrar.py`), qui
tient la registration en vie : 401→digest automatique (3 retries), refresh périodique,
contact **pointant sur B2BUA** (`sip:<exten>@<b2bua-host>:5160`) pour que Wazo renvoie
les appels vers le relay.

**Preuves (tcpdump + log registrar, VM Wazo)** :

```
REGISTER sip:asterisk  → 401 Unauthorized        (demande d'auth)
REGISTER sip:asterisk  (CSeq+1, digest OK)       (réponse auto Sippy)
SIP/2.0 200 OK
Contact: <sip:5100@127.0.0.1:5160>;expires=59   ← contact = B2BUA:5160
```

- **Contact actif** dans l'AOR : `5100@asterisk/sip:5100@127.0.0.1:5160`.
- **Refresh périodique validé** : re-REGISTER observés aux ~59 s (2 cycles), chacun 200
  OK.

**Deux points d'intégration Sippy à connaître** (source du bug « REGISTER envoyé, 401
jamais traité ») :

1. **`ED2.loop()` doit tourner sur le thread principal.** Le TM n'a aucun loop interne :
   les réponses (401/200) arrivent via `AsyncReceiver` → `ED2.callFromThread()`, qui
   n'est servi que par `ED2.loop()`. Sans lui, la transaction client expirait
   silencieusement (le 401 n'était jamais lu). C'est ce que fait `b2bua.py` (loop
   principal, SIGTERM → `breakLoop`).
2. **`Expires`** : Sippy ne pose l'expires qu'en **paramètre du Contact**
   (`;expires=N`), qu'Asterisk 22 ignore (applique le défaut 3600). Il faut forcer
   l'en-tête **top-level** `Expires`
   (`SipHeader(name='expires', body=SipExpires(number=N))`). Le UAS (Asterisk) reste
   souverain sur l'expires accordé (`expires=59` observé avec demande 30) : l'agent
   rafraîchit au cadence **accordée**, comportement RFC 3261 correct.

**Cible de production** : le registrar devient le **sidecar** du relay (B2BUA) — 1 agent
par user Wazo (liste fournie par Odoo `wazo_phone`, extensions + secrets), contact →
B2BUA, process supervisé (s6/supervisord), `ED2.loop()` en thread principal. Le B2BUA
(relay) et le registrar (registration) forment la paire : **1 process d'infrastructure
SIP par user, N onglets gratuits** sur le WSS B2BUA.

## 15. P3.1b — SIP-over-WSS relay (challenges retournés) — validé, digest à clore

**Objectif** : prouver le maillon manquant entre le fan-out (connexions WSS, §13.4) et
le softphone navigateur : un message SIP **envoyé en WSS** (comme le ferait SIP.js) est
relayé vers Wazo **et les réponses reviennent sur le même socket WSS**.

### 15.1 Mécanisme de routage WSS de B2BUA (source)

- **Entrée** : `Wss_server.ws_to_sip` reçoit la frame texte →
  `ED2.callFromThread(self.handle_read, ...)` → TM. Chaque connexion est indexée :
  `connections[conn_id] = websocket` avec `conn_id = f'{websocket.id}.invalid'`
  (`websocket.id` = UUID **stable** de la connexion, vérifié websockets 17).
- **Routage retour** : `SipTransactionManager.handleIncoming` (chemin WSS) pose
  `via0.params['received'] = ra.received` (= `conn_id`) dans le Via du message. La
  réponse copie le Via → `getTAddr()` lit le param `received` comme « host » →
  `monitor_queue` cherche `connections[received]` et
  `websocket.send(response, binary=True)`.

### 15.2 Bug B2BUA (upstream) identifié + corrigé

La condition d'origine (copie **site-packages**, celle que B2BUA charge — attention :
B2BUA importe `sippy` depuis le **venv**, PAS le clone `/opt/sippy-demo/b2bua/sippy/`) :

```python
if ahost != rhost:  # ahost = host du Via, rhost = IP client
    via0.params["received"] = ra.received
```

Pour un client **local** (VM/localhost, `127.0.0.1` = host du Via) la condition est
fausse → pas de `received` → la réponse retombe sur l'IP → `monitor_queue` ne trouve pas
la websocket dans `connections` → **toute réponse destinée à un client WSS local est
dropped** (`Invalid address ... not in connections` × N, retransmissions TM 60 s).

La version du **clone** (upstream plus récente) contient déjà le fix :
`if ahost != rhost or ra.transport == 'wss':`. **Fix appliqué sur la copie
site-packages** (`SipTransactionManager.py`, ~ligne 349) :

```python
if ahost != rhost or ra.transport == "wss":
    via0.params["received"] = ra.received
```

### 15.3 Preuves

```
>> REGISTER  (WSS → 9876)
<- SIP/2.0 401 Unauthorized   (challenge digest, Server: Sippy B2BUA)
   → re-reçu sur le MÊME socket WSS, routé via received=<uuid>.invalid
>> INVITE sip:1005@asterisk   (WSS → 9876)
<- SIP/2.0 100 Trying
<- SIP/2.0 401 Unauthorized   (challenge de Wazo/Asterisk, relayé)
   → aussi re-reçu sur le même socket WSS
```

Le **relay stateful du navigateur** est donc ouvert dans les deux sens. Les frames de
réponse arrivent en **binary** (à connaître côté SIP.js : `binary: true` implicite,
c'est le comportement standard du WSS B2BUA).

### 15.4 Digest client (formule Sippy exacte, lue dans la source)

Pour qop=auth, algorithme MD5 (`SipAuthorization.py` : `DigestCalcResponse`) :

```
HA1      = MD5(username:realm:password)
HA2      = MD5(METHOD:uri)              ← PAS de body, PAS de nonce/nc/cnonce
response = MD5(HA1:nonce:nc:cnonce:qop:HA2)
```

Header à renvoyer (format Sippy, **`username` et `uri` obligatoires** — pjsip rejette
sinon) :
`Digest username="…",realm="…",nonce="…",uri="…",response="…",algorithm=MD5,qop=auth,nc=00000001,cnonce="<hex8>"[,opaque="…"]`

La re-demande **doit garder le même branch/From/To** (transaction inchangée) — ajouter
un tag From la casse.

### 15.5 État — P3.1b ✅ VALIDÉ

- ✅ **Relay WSS bidirectionnel** (challenges reviennent sur le socket client).
- ✅ **Fix B2BUA appliqué** (site-packages) — `.bak_poc` conservés.
- ✅ **e2e complet** (`poc/test_webrtc_e2e.py`, md5 `9b91f142…`) :
  ```
  REGISTER via WSS  -> 200 OK  ✅   (challenge → digest Sippy → 200)
  INVITE   via WSS  -> SIP/2.0 404 Not Found  (réponse DE WAZO, endpoint 1005 absent)
  e2e SIP-over-WSS  -> VALIDE  ✅
  ```
  La **boucle navigateur → B2BUA → Wazo** est ouverte dans les deux sens ; le 404 prouve
  que le routage atteint Wazo (pas un refus local B2BUA).

**Le fix décisif (digest)** : le hand-craft du header `Authorization` (créé en string)
**crashe B2BUA** — celui-ci re-parse le corps via `SipAuthorization.parse()` (ligne 82 :
`for name,value in …split('=')`), qui **mal traite tout corps non-sérialisé-par-Sippy**
(`ValueError: not enough values to unpack`). Le registrar passe parce qu'il **sérialise
un objet `SipAuthorization`** (généré par
`challenge.genAuthHF(user, passw, method, ruri, qop)`), pas une string.

→ Le client **parse la string en `SipRequest`** (parseur Sippy), **délègue le digest à
`challenge.genAuthHF()`** (code natif, §15.4) et **sérialise avec `str(req)`** (Sippy) —
byte-identique au registrar. C'est le même chemin que `SipRegistrationAgent` (registrar
qui marche). **SIP.js dans le navigateur fait exactement ça** (génère le digest via sa
propre lib, renvoie un objet).

Reste avant de clôturer P3.1b (cosmétique, non bloquant) :

- Retirer les **traces debug** (`LOAD=`, `MONQ`) de `Wss_server.py` site-packages +
  redémarrage B2BUA propre (voir `FINALIZE_P3_1B.md`).
- Documenter les 2 patches B2BUA (TM WSS routing + rien d'autre en prod ; le debug est à
  retirer).

---

## 16. P3.2 — Multi-user (N users dans la boucle) — état + prouvas

> §11 définit P3.2 comme « appel sortant, hold/transfer, DTMF, CDR branché ». **Ce qui
> suit est le PREREQUIS de cette phase** : prouver que le relay gère **N users** (N
> registrations, N endpoints) et pas un seul. Sans ça, pas d'appel sortant multi-device.
> Cet §16 documente les prouvas + la méthode.

### 16.1 Prouvé (2026-09-23)

**Multi-agent registrar (cœur P3.2)** — `poc/wazo_registrar.py` boucle
`for exten, pw in users:` → **un `SipRegistrationAgent` par extension**, chacun avec sa
boucle de REGISTER indépendante. Exécution réelle (5100 + 5101) :

```
START user 5100 → ... (contact 127.0.0.1:5160)
START user 5101 → ... (contact 127.0.0.1:5160)
registrar en vie — 2 agent(s), exp=3600s
[5100] REGISTER 200 OK — refresh dans 3599s     ← 5100 dans Asterisk
[5101] REGISTER échec — re-essai dans 60s       ← 5101 pas encore chargé
```

Le registrar **scale à N** sans changement (boucle `users.txt`).

**Création d'endpoint via API confd (voie prod)** — la création passe par `POST /lines`
**avec `endpoint_sip` embarqué** (flow prouvé par le module `wazo_phone` + endpoint
1005), **pas** `POST /endpoints/sip` séparé. Le payload relay-ready (celui que le
registrar doit authentifier) :

```python
{
    "context": CONTEXT,
    "extensions": [{"exten": EXTEN}],
    "endpoint_sip": {
        "auth_section_options": [["username", EXTEN], ["password_digest", f"MD5:{HA1}"]],
        "endpoint_section_options": [["context", CONTEXT], ["callerid", f'"{NOM}" <{EXTEN}>']],
        "aor_section_options": [["max_contacts", "10"]],
        "identify_section_options": [["match", f"username:{EXTEN}"]],
    },
}
# HA1 = md5("<exten>:asterisk:<password>").hexdigest()
```

→ `POST /lines` **201** + `POST /extensions` 201 + `POST /users` 201 +
`PUT /users/{id}/lines/{line}` 204. Testé sur **1011** (chaîne complète créée, endpoint
`m0kxsfvz`, `identify match username:1011`).

### 16.2 Découvertes critiques (épinglées)

1. **La plage du contexte Wazo filtre les extensions.** `POST /lines` renvoie **400 «
   outside of range »** si l'extension est hors plage. **1001-1005 sont dans la plage**
   ; **5100-5199 (marge POC) sont HORS plage**. C'est pour ça que 5100 marche : c'est un
   **fichier pjsip manuel** (`90-poc-b2bua.conf`) qui **bypasse** le modèle de contexte
   Wazo. **Multi-user via l'API confd ⇒ extensions DANS la plage.**
2. **confgend ne génère dans Asterisk que les endpoints SIP liés à une line.** Un
   endpoint créé séparément (`POST /endpoints/sip` sans line) n'apparaît JAMAIS dans
   `pjsip.conf` (pas `wazo-confgen`, même sans `--cached`, même après purge du cache).
   D'où le KO de 5101 (endpoint standalone, pas de line). **Le flow « line +
   endpoint_sip embarqué » est la seule voie.**
3. **Le PUT `/lines/<id>` avec payload partiel CLOBBER** la line (remet `users=null`,
   `endpoint_sip=null`, …). Toujours PUTer le payload complet.
4. **`password_digest` = `MD5:<HA1>`** (HA1 pré-calculé). Le registrar Sippy
   (`genAuthHF`) fait le double-hash à partir du **mot de passe clair** → il faut
   `MD5:HA1` pour qu'il auth (extrait 5100). Les endpoints **WebRTC-natifs** du module
   (`_build_endpoint_sip_payload`) n'ont que `username` (pas `password_digest`) car leur
   registration passe par le compte authd + `/api/asterisk/ws`, **pas** par le registrar
   relay.
5. **Identification par NOM D'AOR, pas par username** (découverte §16.3). L'endpoint
   généré par Wazo confgen porte un nom d'AOR = id endpoint aléatoire (ex : `m0kxsfvz`).
   pjsip matche `domaine/utilisateur` → AOR sur ce **nom** : le REGISTER doit être
   `From: sip:<aor_name>@<domain>` avec `username` d'auth = extension. Le fichier manuel
   5100 contournait le problème car son nom AOR = son extension.

### 16.3 Découverte critique — nom AOR généré ≠ extension (BLOQUANT)

L'endpoint **généré** par Wazo confgen (via `POST /lines` + `endpoint_sip` embarqué)
reçoit un **nom d'AOR = ID d'endpoint aléatoire** (ex : `m0kxsfvz`), **pas**
l'extension. pjsip fait le matching **`domaine/utilisateur` → AOR sur le NOM de l'AOR**,
pas sur le `username` de l'auth. Conséquence : un REGISTER `From: <sip:1011@asterisk>`
(auth username `1011`) est **rejetté (401 persistant)** car aucun AOR ne s'appelle
`1011`.

- Endpoint **manuel** (fichier pjsip) : le nom AOR = l'extension (`[5100@asterisk]`) →
  `From: sip:5100@asterisk` matche.
- Endpoint **généré Wazo** : le nom AOR = id endpoint (`[m0kxsfvz]`) →
  `From: sip:m0kxsfvz@asterisk` (auth username `1011`) matche.

**Preuve** (test direct digest, VM 22:30) : `From=sip:m0kxsfvz@asterisk` + auth
`username=1011` + `password_digest=MD5:9521…` → **200 OK** (tous domaines testés :
`asterisk`, `m0kxsfvz`, `default`). Le REGISTER doit donc utiliser le **nom de l'AOR**
dans `From`/`To`/`Contact`, **l'extension** seulement dans l'Authorization.

### 16.4 Adaptation du registrar — format `users.txt` 3 champs

`wazo_registrar.py` gère maintenant :

```
<exten>|<fichier-pass>                # endpoint manuel : AOR = exten
<aor_name>|<exten>|<fichier-pass>     # endpoint genere Wazo : AOR = aor_name
```

Le `aor_name` (champ 1) alimente `From`/`To`/`Contact` ; l'`exten` (champ 2) alimente le
`username` Authorization. Les 2 champs restent valides pour les endpoints manuels
(AOR=exten).

### 16.5 État — P3.2 multi-user **VALIDÉ** (2026-09-23 22:28)

```
START user 5100 (aor 5100)     -> (('127.0.0.1', 5060), 'udp')
START user 1011 (aor m0kxsfvz) -> (('127.0.0.1', 5060), 'udp')
[22:28:00][5100] REGISTER 200 OK — refresh dans 3599s
[22:28:00][1011] REGISTER 200 OK — refresh dans 3599s
```

**2 REGISTER 200 OK simultanés** via le relay WSS : 5100 (endpoint manuel) + 1011
(endpoint généré par Wazo confgen). Le registrar multi-agent tient N users ; l'endpoint
généré s'authentifie avec son nom AOR (découverte §16.3).

### 16.6 e2e SIP-over-WSS 1011 — VALIDÉ (2026-09-23 22:42)

`test_webrtc_e2e.py --user 1011 --aor m0kxsfvz --target 1005` (client navigateur simulé
sur le WSS 9876 de B2BUA) :

```
CONNECTE wss://127.0.0.1:9876 subprotocol=sip
REGISTER via WSS  -> 200 OK   OK      (AOR m0kxsfvz, auth 1011)
INVITE   via WSS  -> 488 Not Acceptable Here
e2e SIP-over-WSS  -> VALIDE
```

Le **488** (et non 401) prouve que **l'auth INVITE passe** : l'INVITE est routée jusqu'à
Wazo puis rejetée pour cause de **SDP vide** (PoC sans média) — exactement le même
comportement qu'un client WebRTC réel avant négociation. Contrôle 5100 (endpoint manuel)
: REGISTER 200 OK, INVITE 404 (1005 absent du dialplan POC). Les deux users sont donc
**opérés via le relay WSS** avec auth par AOR.

**Règle générale (découverte §16.3)** : pour un endpoint **généré par Wazo confgen**,
TOUS les messages (REGISTER, INVITE, …) doivent porter
**`From: sip:<aor_name>@<domain>`** (aor_name = id endpoint aléatoire) avec `username`
d'auth = l'extension. L'`aor_name` est à récupérer via `GET /lines` →
`endpoint_sip.name` (cf. `p32_create_inrange_user.py`).

### 16.7 Ce qui reste (P3.2 à finir)

- ✅ **Registrar multi-agent** — prouvé (2 users 200 OK simultanés, 22:28).
- ✅ **2 users dans le relay WSS** — 5100 + 1011 enregistrés.
- ✅ **e2e SIP-over-WSS 1011** — REGISTER 200 OK + INVITE authée (488 SDP vide), prouve
  le fan-out WSS sur un user généré (22:42).
- ⏳ **Appel sortant + hold/transfer + DTMF + CDR branché** (cœur §11) — en partie via
  le widget (P3.3) ; CDR déjà en place dans le module.
- ⏳ **Intégration registrar dans le process B2BUA** (option B) ou sidecar dédié — le
  registrar tourne aujourd'hui en process séparé.
- ⏳ **`maxwebsocketclients=100`** (P3.0, pas encore appliqué).
- ⏳ **RTPProxy** (Phase C, NAT-safe, C) — média.

**Conclusion** : le relay **scale à N** (registrar multi-agent prouvé). La méthode de
création multi-user via l'API confd est **validée** (flow « line + endpoint_sip embarqué
», extensions dans la plage, `MD5:HA1`, `identify username`). Le seul maillon restant
est **opérationnel** (charger 1011 dans Asterisk + retest) — pas d'architecture à
revoir.

### 16.8 État P3.3 — Softphone navigateur (2026-09-24)

**Objectif** : softphone WebRTC (SIP.js) **intégré dans Discuss** (pattern du module
Enterprise `voip`) pour un endpoint Wazo généré.

**Livré (validé)** :

- ✅ **Backend** — `wazo.user.get_softphone_config(user_id)` (RPC) : assemble
  `{ws_url, aor, auth_user, auth_password, domain, display_name, extension}`.
  - **Mapping AOR** (découverte §16.3) : `aor` = nom de l'endpoint généré (champ
    `wazo.user.remote_endpoint_name`, capturé au sync via `POST /lines → endpoint_sip`),
    **distinct** de `auth_user` (l'extension).
  - `ws_url` = URL du relay **B2BUA** (`wazo.softphone_ws_url`), repli sur l'URL Wazo ;
    mot de passe lu en `sudo` (la méthode est la frontière).
  - **15 tests** (AOR, WS URL, domaine, dispo, assemblage, repli) — **75/75 tests** du
    module au vert.

- ✅ **Frontend (squelette OWL, validé syntaxe/XML)** — 5 fichiers dans
  `static/src/softphone/` :
  - `wazo_softphone_service.esm.js` — service OWL `wazo_softphone` (état réactif, cycle
    de vie SIP.js : UserAgent + Registerer, appels sortants/entrants, dégradation propre
    si `SIP` absent). `uri = sip:<aor>@<domain>` + `authorizationUsername = <auth_user>`
    (**le mapping critique**).
  - `wazo_softphone_app.esm.js` — main component : s'injecte dans le **systray**
    - gère l'**overlay** du softphone (`registry.category("systray")` +
      `main_components`).
  - `wazo_systray_item.esm.js` — bouton téléphone (hotkey `Alt+Shift+S`).
  - `wazo_softphone.esm.js` — UI (bandeau d'état + numéroteur + Répondre/Raccrocher).
  - `wazo_softphone_templates.xml` — templates QWeb.
  - Bundle `wazo_phone.assets_sip` = `static/lib/sip.js` (UMD, global `SIP`).

**Reste (P3.3b)** :

- ✅ **Fichier `sip.js` VENDU** (2026-09-24) : `static/lib/sip.js` = SIP.js **0.21.2**,
  UMD, global `SIP`, 1 048 975 octets — copie byte-identique du fichier vendored dans le
  module Enterprise `voip` (bibliothèque tierce BSD, pas de code OEEL). **Lazy-loading**
  : le bundle `wazo_phone.assets_sip` se charge à la demande via `loadBundle()`
  (`@web/core/assets`) — les ~1 Mo ne sont servis que quand le softphone est ouvert
  (comme Enterprise).
- ✅ **Build d'assets réelle validée** (2026-09-24) : pipeline exact du webclient
  (`ir.qweb._get_asset_bundle(...).js()`), **sans erreur** :
  - `web.assets_backend` → 7 887 791 octets, marqueurs `wazo_softphone` /
    `WazoSoftphoneApp` / template `wazo_phone.Softphone` **présents**.
  - `wazo_phone.assets_sip` → 496 136 octets (SIP.js minifié), `SIP` / `UserAgent`
    **présents**.
  - Piège corrigé : `onWillRender` n'existe pas dans ce OWL (owl.js) → remplacé par
    `onWillUpdateProps` + listener sur le bus du service.
- ⏳ **Cœur §11 (P3.3b) — livré et validé (2026-09-24)** : hold / transfer / DTMF + CDR
  branché sur le widget.
  - **Backend** — 2 méthodes sur `res.users` (le contrôleur web browse `res.users` avec
    l'ID de l'utilisateur courant — mécanique confirmée dans
    `odoo/service/model.py::call_kw`, `ids, args = args[0], args[1:]`) :
    - `get_wazo_softphone_config()` — délègue à `wazo.user.get_softphone_config`.
      **Corrige le câblage latent du P3.3a** : l'ancien appel frontend passait l'ID
      `res.users` au modèle `wazo.user` (browse par coïncidence d'ID SQL, non fiable).
      Ici le modèle browse est le bon (`res.users`).
    - `get_wazo_call_log(limit=50)` — CDR de l'utilisateur (appelant OU destination =
      son extension), triés `date_start desc`, bornés. Chaque entrée porte l'autre
      partie (numéro, nom, contact identifié, durée).
    - **9 tests** (délégation config, journal vide/propres/autrui/tri/limit/champs) —
      **84/84 tests** du module au vert.
  - **Frontend** — service (`hold`/`unhold`/`sendDtmf`/`transfer`/`loadCallLog`
    - wiring corrigé + état `held`/`callLog` réactifs) ; API SIP.js **0.21.2 confirmée**
      dans le fichier vendored : `session.hold()`/`unhold()` + `isHeld` (re-INVITE SDP,
      RFC 6337), `sendDtmf(tones)`, `refer(referTo)` (transfert out-of-band, RFC 3515).
      UI : **onglets** « Appel » / « Journal », boutons **Mettre en attente/Reprendre**,
      pavé **DTMF** (0-9, *, #), champ **Transférer**, **journal d'appels** (liste CDR,
      formatage durée/date).
  - **Build d'assets réelle revalidée** : `web.assets_backend` → 7 894 877 octets (+7
    086 vs P3.3a), marqueurs P3.3b **présents** : `get_wazo_softphone_config` /
    `get_wazo_call_log` / `sendDtmf` / `Transférer` / `Mettre en attente` /
    `Aucun appel enregistré`. Zéro erreur de compilation.
- ⏳ **QA navigateur réelle** (appels WebRTC de bout en bout) — e2e déjà prouvé en
  script (§16.6), à confirmer dans le navigateur sur l'instance live (relay B2BUA +
  endpoint 1011).
- ⏳ **Notifications** (appels entrants hors softphone) + **multi-device**.

**État** : P3.3a (backend + squelette UI + SIP.js vendu + build d'assets validée)
**complet et testé** ; **P3.3b (cœur §11 : hold/transfer/DTMF + CDR sur widget) livré et
validé** (84/84 tests, build d'assets sans erreur) — **conservé tel quel en v3**.
**Branchement sur la voie native** (section NORMATIF en tête de document) : **P3.3c ✅**
— `_softphone_ws_url()` retourne `wazo.ws_url`, le paramètre relay
`wazo.softphone_ws_url` est retiré et son override ignoré ; **P3.3d ✅** — l'endpoint
créé par la sync se réfère aux templates `global` + `webrtc` du tenant (au lieu de
réimplémenter leurs options) : payload vérifié **identique à l'endpoint de référence
`webrtc1001`** contre le tenant réel — **89/89 tests**. Reste : P3.3e (arbitrage
multi-onglets), P3.3f (décision SDK), puis P3.4 (démontage du relay).

> ⚠️ **2026-09-24 — PIVOT D'ARCHITECTURE (annule les points relay ci-dessus).** La QA
> navigateur a été faite sur la **voie native** (démo officielle `wazo-webrtc-demo` +
> endpoint `webrtc1001`) : **audio deux sens validé, sans aucun relay dans le chemin**.
> En conséquence, sont **obsolètes** dans cette section : le renvoi à
> `wazo.softphone_ws_url` (le softphone doit pointer sur **`wazo.ws_url`**), le repli «
> URL Wazo » présenté comme un pis-aller, et le point « QA live via relay B2BUA +
> endpoint 1011 ». Le relay (`wazo_registrar.py`, `run_b2bua.sh`, proxy nginx `b2bua…`)
> sort du chemin en **P3.4**.
