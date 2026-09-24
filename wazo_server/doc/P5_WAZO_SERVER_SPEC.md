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
