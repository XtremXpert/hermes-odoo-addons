# P5 — Module `wazo_server` : création et encadrement des tenants

## 1. Pourquoi deux modules

`wazo_phone` est le module **d'un tenant** : il configure une partie du PBX —
postes, groupes d'appel, plages, inventaire, softphone. `wazo_server` est le
module de **celui qui exploite le serveur** : il crée les tenants et fabrique
l'accès de chacun.

La dépendance va dans un seul sens : **`wazo_server` dépend de `wazo_phone`**.
Un tenant installe donc `wazo_phone` seul et n'hérite jamais de la machinerie de
création de tenants ; l'exploitant installe `wazo_server`, qui embarque
`wazo_phone` (dont il réutilise le client et les réglages, plutôt que d'en
écrire un second).

## 2. Ce que l'API permet, vérifié sur le PBX

Tout ce qui suit a été constaté par appel réel, pas déduit d'une documentation.

| Opération | Appel | Constat |
|---|---|---|
| Lister les tenants | `GET /api/auth/0.1/tenants` | 200 — les tenants vivent dans **wazo-auth** |
| Lire un tenant | `GET /api/auth/0.1/tenants/{uuid}` | 200 — champs `name`, `slug`, `parent_uuid`, `contact`, `phone`, `address`, `domain_names`, `default_authentication_method` |
| Créer un tenant | `POST /api/auth/0.1/tenants` | **200**, corps `{name, slug, parent_uuid}` |
| Supprimer un tenant | `DELETE /api/auth/0.1/tenants/{uuid}` | **204** |
| Créer un utilisateur du tenant | `POST /api/auth/0.1/users` **+ en-tête `Wazo-Tenant`** | 200 — **c'est l'en-tête qui décide** du tenant ; `?tenant_uuid=` en chaîne de requête est **ignoré** (mesuré : le compte naît alors dans le maître) |
| Donner les droits d'admin | `PUT /api/auth/0.1/users/{user}/policies/{politique}` | 204 |
| Obtenir un jeton | `POST /api/auth/0.1/token` | 200 — **authentification Basic** (`username:password`), `expiration` jusqu'à **315360000** (10 ans), `/token` au **singulier** |
| Créer le contexte et ses plages | `POST /api/confd/1.1/contexts` | `user_ranges`, `group_ranges`, `queue_ranges`, `conference_room_ranges`, `incall_ranges` sont des champs **écrivables** : un seul appel suffit |

Le plugin `tenant` de **confd est en lecture seule** (aucun `POST`) : ne pas
chercher la création de tenants là-bas. En revanche confd est le seul à dire si
les templates SIP d'un tenant sont générés (`sip_templates_generated: True` dès
la création) — **auth rend `None`** pour ce champ, ce qui laisse croire à tort
que rien n'a été généré.

**Contraintes de validation, à appliquer localement** (un refus local vaut mieux
qu'un 400 au milieu d'une séquence) :

* slug : `[a-zA-Z0-9_]{1,10}` — **10 caractères maximum**, trait d'union exclu
  (`TenantSlug` de `wazo_auth/slug.py`), là où le slug générique accepte `-` et
  80 caractères ;
* les bornes de plage sont portées en **texte** par l'API (`{"start": "1000"}`),
  comme partout dans Wazo.

## 3. Ce que crée `wazo_server`, dans l'ordre

1. **Le tenant** — `POST /api/auth/0.1/tenants` (`name`, `slug`, `parent_uuid`).
2. **Son contexte interne**, plages comprises — `POST /api/confd/1.1/contexts`
   avec l'en-tête `Wazo-Tenant` du tenant neuf. Nom : `ctx-<slug>-internal`,
   plages par défaut `1000-1999` (postes) et `2000-2099` (groupes), ajustables.
   Sans contexte, un tenant neuf est **inutilisable** : `wazo_phone` n'a rien où
   créer un poste, et le repli actuel `'default'` ne correspond à aucun contexte.
3. **Son utilisateur administrateur** — `POST /api/auth/0.1/users` **avec l'en-tête
   du tenant neuf**, mot de passe **généré**. Le paramètre `tenant_uuid` en
   chaîne de requête ne suffit pas : mesuré, l'utilisateur naîtrait alors dans
   le maître, laissant le tenant sans administrateur.
4. **Ses droits** — `PUT /users/{user}/policies/wazo_default_admin_policy`
   (14 ACL, dont `confd.#`).
5. **Son jeton** — `POST /api/auth/0.1/token` en Basic, `expiration` longue,
   conservé côté Odoo et communiqué à l'exploitant du tenant.

Chaque identifiant est consigné **dès qu'il est obtenu**, jamais à la fin : un
échec en cours de séquence doit laisser une trace permettant de reprendre ou de
supprimer (leçon de P4.3d, vérifiée par un test).

## 4. La limite de cloisonnement, mesurée

Un jeton de tenant n'est **pas** une frontière de sécurité. Constaté :

| Appel du jeton du tenant `sonde` | Attendu | Réel |
|---|---|---|
| `confd /users`, en-tête `Wazo-Tenant: test` | refus | **200, 8 utilisateurs lus** |
| `confd /lines`, même en-tête | refus | **200, 11 lignes lues** |
| `auth /tenants` | son seul tenant | **200, les 3 tenants listés** |

Créer la politique **dans** le tenant plutôt que d'utiliser celle du maître ne
change rien : les ACL de Wazo sont des chaînes indépendantes du tenant
(`confd.users.read` ne dit pas *de quel* tenant), et confd honore l'en-tête sans
vérifier que le tenant visé appartient au sous-arbre du jeton.

**Conséquence assumée** : « une instance Odoo par tenant + un jeton par tenant »
cloisonne contre les erreurs, pas contre un administrateur de tenant décidé, qui
contrôle son Odoo et peut donc lire le jeton en base. La frontière réelle est à
l'**URL** : un point d'entrée par tenant qui impose `Wazo-Tenant` et ignore
toute valeur fournie par le client. Le module n'a rien à changer pour cela : il
lit déjà son URL dans les réglages (P5.5, hors périmètre logiciel).

## 5. Décisions

* **Une instance Odoo par tenant.** Pas de règles d'accès multi-société à
  écrire : chaque installation ne voit que son tenant, et son jeton ne sert
  qu'elle.
* **Un jeton par tenant**, fabriqué par `wazo_server`, jamais saisi à la main.
* **Suppression gardée** : elle énumère ce qui va disparaître (utilisateurs,
  lignes, contexte) et refuse tant que des ressources existent, sauf demande
  explicite.
* **Aucun secret en clair hors des champs prévus** : mot de passe et jeton
  vivent dans des champs réservés au groupe gestionnaire, comme
  `sip_password`/`voip_secret` aujourd'hui.
* Le tenant **reçoit** ses coordonnées depuis Odoo ; il ne les devine pas.

## 6. Phasage

| Phase | Contenu | État |
|---|---|---|
| **P5.1** | Client : appel `token` en Basic, `/token` au singulier, expiration longue | ✅ 5 tests |
| **P5.2** | Modèle `wazo.server.tenant` : champs, validation locale du slug | ✅ |
| **P5.3** | Création complète (tenant → contexte → plages → admin → droits → jeton) | ✅ séquence vérifiée |
| **P5.4** | Suppression gardée, remise à l'état initial | ✅ |
| **P5.5** | Vues, menus, droits | ✅ |
| **P5.6** | Vérification en direct | ✅ voir §7 |
| **P5.7** | Reprise d'une création interrompue : relecture et adoption, jamais de doublon | ✅ voir §8 |
| **P5.8** | Fiche de remise au tenant : un bloc à copier, étiqueté comme les réglages | ✅ voir §10 |
| **P6** | Choisir le tenant à administrer, fiche par fiche (en-tête + contexte) | ✅ voir §9 |
| **P7** | Renouveler le jeton d'un tenant vivant, et révoquer l'ancien | ✅ voir §11 |

## 7. Vérification en direct (P5.6)

Tenant `odoo_sonde` créé par le module sur le PBX réel, puis supprimé :

| Observation | Résultat |
|---|---|
| Création par le module | `True`, état `created` |
| Contexte et plages, relus du PBX avec le **jeton du tenant** | étiquette `ctx-odoo_sonde-internal`, postes `1000-1999`, groupes `2000-2099` |
| Comptes du tenant neuf (vus par son jeton) | **total 1** — son seul administrateur |
| Fiche de l'administrateur | `tenant_uuid` = celui du tenant neuf : **né au bon endroit** |
| Jeton | 36 caractères, expiration 2036 (dix ans) |
| Garde de suppression, un poste présent | refus : « porte encore 1 poste(s) et 0 ligne(s) » |
| Suppression | `True`, retour à 2 tenants, aucun résidu |

Le défaut corrigé ici mérite d'être retenu : la **première** version créait
l'administrateur avec le client du maître. Les tests unitaires ne pouvaient pas
le voir — ils remplaçaient `auth`/`conf`, alors que le jeton passe par
`_request` — et la suite était verte. C'est la vérification en direct, en
comparant le `tenant_uuid` de la fiche, qui l'a montré ; deux tests l'encodent
désormais (ils portent sur l'en-tête employé, pas sur l'appel reçu).
**Un transport simulé ne falsifie pas un modèle de l'API** : il faut lire le PBX.

## 8. Reprise d'une création interrompue (P5.7)

Une création qui échoue laisse le tenant en état `error` avec des repères
partiels. La relancer **reprend**, elle ne recommence pas :

| Étape | Si le repère local manque | Si le repère existe |
|---|---|---|
| Tenant | création | rien — `remote_uuid` présent ⇒ jamais de second `POST /tenants` |
| Contexte | relecture de `GET /contexts`, adoption si l'étiquette correspond, création sinon | rien |
| Administrateur | relecture de `GET /users` (en-tête du tenant), adoption par nom d'utilisateur | rien |
| Mot de passe | ─ | sans lui, **refus explicite** : wazo-auth ne le rend à personne | 
| Jeton | toujours refabriqué s'il manque | rien |

Vérifié en direct, après perte simulée des repères locaux : la reprise a adopté
le **même** tenant, le **même** contexte et le **même** administrateur, et le
PBX ne portait qu'**un** contexte et **un** compte. Aucun doublon. Le cas du
mot de passe perdu rend un refus lisible plutôt qu'un tenant sans accès.

Les relèvements n'ont lieu **que** sur une reprise : un tenant créé à l'instant
n'a rien à relire, et ne paie pas deux appels inutiles.

## 9. Choisir le tenant à administrer (P6)

Sur l'instance de l'**exploitant**, le tenant des réglages ne peut plus être
celui de tout le monde. Les fiches qui parlent au PBX (`wazo.user`,
`wazo.ring.group`) reçoivent donc un champ **Tenant Wazo** : c'est lui qui
décide de l'en-tête `Wazo-Tenant` et du contexte employés. Deux postes du même
modèle peuvent appartenir à deux clients — et un groupe d'appel ne peut plus
mélanger les membres de deux tenants.

Vérifié en direct, deux fiches sur une seule instance :

| Fiche | En-tête envoyé | Contexte employé | Ce que le PBX rend |
|---|---|---|---|
| Tenant choisi (neuf) | `67bfb7b8…` | `ctx-odoo_sel-internal-…` | **0 poste, 1 contexte** |
| Aucun tenant choisi | `7f001a0b…` (réglages) | `ctx-test-internal-…` | **8 postes, 1 contexte** |

Le champ est **vide par défaut** : on retombe alors sur les réglages, ce qui
laisse un tenant installer `wazo_phone` seul — chez lui, le champ n'existe
nulle part. Il est réservé au groupe gestionnaire, comme les tenants eux-mêmes,
et il apparaît en permanence : colonne de liste, champ de formulaire, filtre et
groupement par tenant.

### Le piège de l'ordre d'héritage

`wazo_server` ne modifie pas `wazo_phone` : il étend ses méthodes
(`_wazo_tenant_uuid`, `_wazo_line_context`) par un mixin,
`wazo.server.tenant.selection`. Encore faut-il que ce mixin **passe devant**
`wazo.extension.mixin` :

    _inherit = ['wazo.user', 'wazo.server.tenant.selection']   # perd
    _inherit = ['wazo.server.tenant.selection', 'wazo.user']   # gagne

Mesuré : la **première** entrée de `_inherit` l'emporte. Dans le premier cas la
chaîne est `WazoExtensionMixin -> WazoServerTenantSelection` et ce sont les
réglages qui décident — silencieusement, sans erreur ni avertissement. Cinq
tests portent désormais sur l'en-tête et le contexte réellement employés.

### Ce qui garde le tenant des réglages

Trois chemins ne suivent pas la fiche, volontairement : le **journal des
appels** (lecture), l'**écran de réglages** (il teste la connexion telle qu'elle
est réglée), et l'**inventaire** des postes (modèle transitoire, sans fiche à
interroger). Sur l'instance de l'exploitant, ces écrans montrent le tenant des
réglages.

À noter, pour qui écrit une sonde : `WazoClient(env, tenant_id=None)` **retombe
sur les réglages**, ce n'est pas « sans en-tête ». Toute lecture part donc avec
l'en-tête du tenant réglé — ce qui explique qu'une liste de tenants paraisse
courte : elle est vue **depuis ce tenant**.

## 10. Fiche de remise au tenant (P5.8)

L'exploitant ne recopie pas les valeurs une à une depuis un formulaire : la
fiche de tenant calcule un **bloc à copier**, dont les libellés sont ceux des
réglages de `wazo_phone` — un champ mal rempli se voit alors tout de suite.

    Coordonnées du tenant « Client Alpha »

    Réglages → Téléphonie Wazo
        URL du serveur Wazo : https://wazo.example.com
        Token API Wazo      : ****
        Tenant Wazo (UUID)  : 1855d676-988d-4011-a3a9-22906df7c13c
        Contexte des lignes : ctx-odoo_sonde-internal-99cbe378-…

    Administrateur du tenant dans Wazo :
        odoo_admin / ****

    Jeton valable jusqu'au 2036-09-21 15:58:56. Il ne s'agit pas d'une
    session : le jeton sert à l'intégration, et il disparaît avec le tenant.

Le bloc est **calculé à la lecture**, non stocké : l'URL du serveur est relue à
la demande, donc la fiche reste juste même si les réglages changent après coup.
Il est **réservé au groupe gestionnaire** — il porte le jeton et le mot de passe.
Un tenant qui n'existe pas encore sur Wazo rend une phrase qui le dit, plutôt
qu'un bloc à moitié vide ou, pire, un jeton vide présenté comme un jeton.

## 11. Renouveler le jeton d'un tenant vivant (P7)

Le jeton est le secret remis au client. Tant qu'il n'y avait que créer et
supprimer, un jeton fuité — sauvegarde de l'Odoo du client, poste de travail,
départ d'un employé — ne pouvait pas être repris : la seule sortie était une
suppression, que la garde refuse tant que le tenant porte des postes, et qui
emporterait le client avec elle.

`action_rotate_token` fabrique donc un jeton neuf avec les identifiants
d'administrateur **déjà conservés sur la fiche** (`POST /token` en Basic, dix
ans), puis révoque l'ancien (`DELETE /token/{jeton}` — route **ouverte** à qui
connaît le jeton : mesuré, `security: - {}` dans l'API de wazo-auth).

L'ordre est **émettre, puis révoquer**. Une révocation ratée laisse deux jetons
vivants, l'ancien mourant à son expiration — réparable —, au lieu d'un client
dont le jeton vient d'être tué avant que son Odoo ait reçu le neuf. Et une
révocation ratée n'est jamais tue : la fiche le dit (`token_revocation_note`,
`previous_token_revoked`), parce qu'un secret qui reste valable doit se savoir.

Vérifié en direct sur un tenant neuf, du point de vue de wazo-auth lui-même :

| Moment | Ancien jeton | Nouveau jeton | Ce que porte le tenant |
|---|---|---|---|
| avant | vivant (HTTP 200) | — | 1 contexte, 1 compte |
| après | **mort (HTTP 404)** | vivant (HTTP 200) | 1 contexte, 1 compte |

Le tenant n'a pas bougé d'un pouce : c'est tout l'objet de la manœuvre —
reprendre le secret **sans** détruire le client. Le jeton ne se recopie ni dans
la note d'échec ni dans le journal : la note est lue par des humains, et le
jeton voyage déjà, en clair, dans le chemin de l'appel qui le révoque.
