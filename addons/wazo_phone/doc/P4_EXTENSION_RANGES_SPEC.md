# P4 — Plages d'extensions et groupes d'appel (Wazo)

Statut : **spécifié**, implémentation à venir (TDD).
Périmètre : administration téléphonique (postes, groupes). Le softphone (P3) n'est
pas touché par ce document.

## 1. Décisions

| Question | Décision |
|---|---|
| Qui choisit le numéro de poste ? | **Le humain, toujours.** Aucune allocation automatique. Mais un numéro hors plage, ou appartenant à la plage d'un autre type, est **refusé** avant tout appel à Wazo. |
| Jusqu'où va la gestion des types ? | **Les postes utilisateurs *et* les groupes d'appel créés depuis Odoo**, avec leur plage dédiée. |

## 2. Faits vérifiés (PBX `wazo-test`, 2026-09-24)

Les plages sont **stockées par Wazo**, par contexte — donc par tenant. La table ne porte
pas « range » dans son nom : c'est `contextnumbers` (`context`, `type`, `numberbeg`,
`numberend`, `didlength`). Une recherche sur `%range%` les manque.

Configuration constatée sur le tenant `test` :

| Type | Plage déclarée |
|---|---|
| `user` | 1000 – 1999 |
| `group` | 2000 – 2099 |
| `queue`, `conference`, `incall` | **aucune plage** |

L'API les sert **calculées** :

```
GET /1.1/contexts/{context_id}/ranges/{range_type}?availability=available|all
```

Réponses relevées en direct sur le contexte `test` (id numérique `1`) :

```
user   disponible : 1000-1000, 1006-1010, 1012-1999   complet : 1000-1999
group  disponible : 2002-2099                         complet : 2000-2099
queue / conference / incall : vides
```

Deux règles en découlent, et elles font autorité :

1. **`available` découpe la plage en sous-plages de numéros libres.** Les trous de la
   plage `user` correspondent exactement aux postes occupés (1001-1005, 1011).
2. **Toute extension existante est indisponible, même non attribuée.** Démonstration
   sur ce PBX : côté `group`, la plage disponible commence à **2002** — 2000 *et* 2001
   sont comptés pris. 2000 est le vrai groupe ; 2001 est une extension orpheline
   (`typeval = 0`). Conséquence : **on ne recalcule pas la disponibilité soi-même**,
   on lit celle du PBX.

`{context_id}` est l'**id numérique** du contexte. Les champs `context` des endpoints et
des extensions portent le **nom** (ex. `ctx-test-internal-…`) : une résolution
nom → id est nécessaire, à faire une fois et à mettre en cache.

## 3. Contrat d'API retenu (relevé dans les specs installées, pas supposé)

| Besoin | Appel |
|---|---|
| Numéro libre d'un type | `GET /1.1/contexts/{id}/ranges/{type}?availability=available` |
| Plage déclarée d'un type | `GET /1.1/contexts/{id}/ranges/{type}?availability=all` |
| Contexte par son nom | `GET /1.1/contexts` (filtré par `Wazo-Tenant`) |
| Créer un groupe | `POST /1.1/groups` — `label`, `ring_strategy`, `timeout`, `user_timeout`, `retry_delay`, `ring_in_use` |
| Créer une extension | `POST /1.1/extensions` — `{exten, context}` |
| **Associer** l'extension au groupe | `PUT /1.1/groups/{uuid}/extensions/{extension_id}` |
| Membres | `PUT /1.1/groups/{uuid}/members/users` — `{users: [{uuid, priority}]}` |
| Supprimer | `DELETE /1.1/groups/{uuid}` |

Points de contrat qui piègent :

* **L'extension d'un groupe n'est pas un champ du `POST /groups`.** L'association est un
  appel distinct, et l'extension doit **exister avant**. Trois appels, donc, dans cet
  ordre : groupe → extension → association.
* Dans `POST /groups`, **`name` est en lecture seule** : le nom convivial se passe par
  `label` (le `name` est généré par Wazo, comme les noms d'endpoints).
* `PUT /groups/{uuid}/members/users` **remplace l'ensemble** : il supprime tout membre
  non listé. C'est idempotent et donc adapté à une synchro, mais un envoi partiel
  vide le groupe.
* Les membres sont désignés par **`uuid` d'utilisateur**, pas par id numérique. Or
  `wazo.user` ne stocke aujourd'hui que `remote_user_id` (entier) : **il manque l'uuid**.
* `ring_strategy` : `all` (défaut), `linear`, `random`, `least_recent`, `fewest_calls`,
  `memorized_round_robin`, `weight_random`.
* **Les bornes des plages sont des chaînes** : `{"start": "1000", "end": "1000"}`.
  Wazo garde les extensions en texte pour préserver un éventuel zéro de tête ; c'est
  cette forme textuelle qui repart vers l'API. La comparaison se fait donc sur la
  **valeur numérique** — `999` précède `1000`, ce qu'une comparaison textuelle inverse —
  mais sans jamais convertir la valeur transmise. Une fixture de test en entiers fait
  passer les tests alors que le PBX réel échoue : les fixtures doivent reproduire les
  chaînes.

## 4. Règles de validation

Pour un numéro saisi, sur un contexte donné :

| Cas | Résultat |
|---|---|
| Dans la plage du type attendu et libre | accepté |
| Dans la plage du type attendu mais déjà pris | refusé — « déjà attribué » |
| **Dans la plage d'un autre type** (ex. 2000 en poste utilisateur) | refusé — « réservé aux groupes » |
| Hors de toute plage déclarée | refusé — « hors plage » |
| Le type n'a **aucune plage déclarée** | refusé, avec un message qui le dit (cas `queue`, `conference`, `incall`) |

Les trois refus doivent être **distincts** dans le message : « hors plage », « réservé à
un autre type » et « déjà pris » n'appellent pas la même correction. D'où **deux** appels
au PBX : `availability=all` pour l'appartenance, `availability=available` pour la
disponibilité.

Vérifier aussi que le numéro n'est pas **déjà porté en local** par un autre
enregistrement Odoo (même contexte) : le PBX peut ne pas être consultable, et deux
enregistrements Odoo ne doivent jamais viser le même numéro.

Ces règles valent pour un poste **absent** de Wazo. S'il y est **déjà**, un
contrôle préalable s'applique (§8) : un poste en service chez quelqu'un, ou une
ressource résiduelle, est refusé — seule la relance après échec peut reprendre un
poste existant.

## 5. Modifications du module

| Élément | Nature |
|---|---|
| `services/wazo_client.py` | `context_id(name)` (résolu puis mis en cache), `ranges(type, availability)`, `available_extensions(type)` |
| `models/voip_bridge.py` | expose les helpers de plage au modèle ; repli défensif : une lecture de plage qui échoue **ne casse pas** une synchro, elle refuse la validation |
| `models/wazo_user.py` | validation de `extension` (contraintes + messages distincts) ; ajout de `remote_user_uuid` (requis pour les membres de groupe) |
| `models/wazo_ring_group.py` | **nouveau** : `name`, `extension`, `ring_strategy`, `user_timeout`, `retry_delay`, `timeout`, `member_ids` (→ `wazo.user`), état de synchro, actions synchroniser/relancer/supprimer |
| `models/wazo_extension_mixin.py` | **nouveau** : règles de poste **partagées** par les utilisateurs et les groupes (plage de son type, plage d'un autre type, disponibilité, reprise), `_extension_type` déclarant le type, et `_wazo_line_context()` |
| `views/wazo_ring_group_views.xml`, `security/ir.access.csv`, `views/wazo_menus.xml` | vues liste/formulaire, accès (lecture / gestion), entrée de menu |
| `models/wazo_context_inventory.py` | **nouveau** : inventaire **transitoire** du contexte — poste, rattachement, orpheline, plage, fiche Odoo ; reconstruit depuis le PBX à chaque chargement |
| `views/wazo_context_inventory_views.xml` | liste (filtre « Orphelines », regroupement par rattachement), formulaire, action |

`wazo.line_context` reste le contexte de travail : il **identifie déjà le tenant**, donc
la plage est bien celle du tenant. Aucun paramètre de plage en configuration.

## 6. Phasage

| Phase | Contenu | Critère de sortie |
|---|---|---|
| **P4.1** ✅ | Lecture des plages : résolution du contexte par nom, `ranges()`, cache | **Fait** : 18 tests unitaires verts + vérification live sur le PBX réel. Le live a révélé que les bornes sont textuelles (§3) — les tests unitaires, avec des fixtures entières, l'avaient manqué. |
| **P4.2** ✅ | Validation du poste utilisateur (plage, type, unicité locale) | **Fait** : 15 tests, suite complète **127/127**. Verdicts vérifiés en direct contre le PBX. |
| **P4.2b** ✅ | Poste déjà présent : reprise légitime ou poste d'un autre | **Fait** : le critère est l'état de la fiche (§8). **129/129** en suite complète ; verdicts live : `1000` accepté, `1001` / `1011` / `2000` / `2005` / `5101` refusés. |
| **P4.3** ✅ | Modèle `wazo.ring.group` + création en quatre appels (groupe, extension, association, membres) + version Odoo de la validation | **Fait** : 16 tests de groupe + 3 d'accès, suite complète **148/148**. Vérifié **en direct** : groupe `ee34ac46…` (poste 2002) créé depuis Odoo, relu du PBX, et la plage libre des groupes est passée de `2002-2099` à `2003-2099` (§9). |
| **P4.3b** ✅ | Reprise de l'uuid des utilisateurs synchronisés avant le champ | **Fait** : 5 tests. Live : uuid effacé en base → relu seul du PBX, conforme au propriétaire de la ligne. |
| **P4.3c** ✅ | Motif du libellé de groupe, imposé par Wazo | **Fait** : 4 tests. Live : `Réception (accueil)` refusé **en local**, au lieu d'un 400 de l'API en pleine synchro. |
| **P4.3d** ✅ | Échec en cours de séquence : ne pas laisser d'orphelin | **Fait** : 1 test, RED observé (`False != 'grp-uuid-3'`). Les identifiants sont consignés dès leur obtention. |
| **P4.4** ✅ | Inventaire du contexte, signalement des orphelines (2001, 5101) | **Fait** : 9 tests, suite complète **167/167**. Inventaire réel : 10 postes, **2 orphelines** (`2001` en plage, `5101` hors plage), 2 postes tenus par une fiche Odoo (§10). |
| **P4.5** ✅ | Priorité de sonnerie des membres (stratégie « un après l'autre ») | **Fait** : 3 tests, suite complète **170/170**. Reprise des membres déjà liés vérifiée (`1 membre repris`), priorité **relue du PBX** après écriture. §11 |

## 7. Hors périmètre (explicite)

* **Configurer les plages depuis Odoo** : l'API n'expose que la **lecture** des plages.
  Elles se définissent côté Wazo. Si un jour il faut les piloter depuis Odoo, c'est un
  autre contrat, à relever avant de promettre quoi que ce soit.
* Allocation automatique de poste (décision : refusée).
* Files d'attente, conférences, SVI : les plages existent dans l'API, mais aucun modèle
  Odoo n'est prévu ici.
* Nettoyage des extensions orphelines : P4.4 les **signale**, ne les supprime pas.

## 8. Poste déjà présent : reprise légitime ou poste d'un autre (P4.2b)

Un poste peut déjà exister côté Wazo pour deux raisons opposées : c'est la
**reprise** d'une synchronisation interrompue, ou c'est **le poste de quelqu'un
d'autre**. Les deux se présentaient identiquement, d'où un trou : `1011` (poste
d'un utilisateur) et `5101` (ressource orpheline) passaient sans contrôle.

### Le critère : l'état de la fiche, pas une heuristique

L'état `error` signifie qu'une tentative a eu lieu puis a échoué — et une
synchronisation interrompue laisse ses ressources distantes derrière elle, sans
que leurs identifiants survivent au rollback de la transaction Odoo. La reprise
est donc **légitime**, et seule, dans ce cas.

L'état `new` signifie qu'**aucune tentative n'a eu lieu** : rien de ce qui
existe côté Wazo ne peut venir de cette fiche. Tout poste déjà présent y est par
conséquent celui d'un autre — refus.

`action_retry_sync` n'est qu'un appel à `action_sync_wazo` avec l'état `error` :
le critère couvre donc exactement le chemin de relance, sans le modifier.

### Les deux refus, en état `new`

| Situation du poste côté Wazo | Verdict |
|---|---|
| Rattaché à un **groupe, une file, une conférence, un renvoi ou un parc** | refus — « appartient déjà à … » |
| Rattaché à une **ligne en service** (ligne rattachée à un utilisateur) | refus — « déjà en service sur Wazo (utilisateur « … ») » |
| **Présent sans aucun rattachement** (ressource résiduelle) | refus — « existe déjà sans être attribué (ressource résiduelle) » |
| Aucune trace côté Wazo | contrôle des plages (voir §4) |

« En service » se lit dans la relation ``Line.users`` de l'API. `GET /users`
rend les lignes de **tous** les utilisateurs en un seul appel — un appel de
plus, seulement quand le poste existe déjà et que la fiche est en état `new`.

### Verdicts mesurés en direct sur le tenant `test`

| poste | état réel côté PBX | verdict |
|---|---|---|
| `1000` | libre, dans la plage des postes | **accepté** |
| `1001` | en service (utilisateur « Test User1 ») | **refusé** |
| `1011` | en service (utilisateur « PoC Multi PoC ») | **refusé** |
| `2000` | rattaché à un groupe d'appel | **refusé** |
| `2005` | libre, mais dans la plage des groupes | **refusé** |
| `5101` | aucune ligne, hors de toute plage | **refusé** |

### Changement de comportement, assumé et documenté

La réutilisation d'un poste existant n'est plus possible au premier essai : elle
est réservée à la relance après échec. Le test `test_sync_reuses_existing_extension`
a été adapté en conséquence — il place désormais la fiche en état `error` avant
de vérifier la reprise, avec le commentaire qui l'explique. Le mécanisme
d'idempotence est donc intact, mais son périmètre est explicite.

Conséquence pour un cas d'usage voisin : **adopter** un utilisateur déjà existant
dans Wazo n'est pas possible par la synchronisation (elle refuserait). Cette
adoption — se rattacher à des identifiants distants existants plutôt que d'en
créer — serait un volet distinct, à spécifier.

## 9. Groupes d'appel créés depuis Odoo (P4.3)

Un groupe d'appel est un poste qui sonne chez plusieurs personnes : il consomme
un numéro de la plage ``group``, comme un utilisateur consomme un numéro de la
plage ``user``. Les règles de poste sont **identiques** — c'est pourquoi elles
vivent maintenant dans ``wazo.extension.mixin``, partagé par les deux modèles,
chacun déclarant seulement ``_extension_type`` (``'user'`` ou ``'group'``).
Dupliquer ce contrôle aurait garanti que les deux copies divergent.

### Quatre appels, dans cet ordre

| # | Appel | Pourquoi à cette place |
|---|---|---|
| 1 | `POST /groups` | Le groupe porte le libellé, la stratégie et les délais. |
| 2 | `POST /extensions` | L'extension doit **exister** avant d'être associée. |
| 3 | `PUT /groups/{uuid}/extensions/{extension_id}` | L'association. |
| 4 | `PUT /groups/{uuid}/members/users` | Seulement s'il y a des membres. |

`name` est en **lecture seule** côté API : Wazo génère `grp-<slug>-<uuid>`.
Le nom convivial passe par `label` — vérifié en direct (le PBX rend
`name = grp-test-8140cf84-…` pour `label = « Groupe QA P4.3 »`). Le module
n'envoie donc jamais `name`.

### Les membres : tout ou rien, et par uuid

* Le corps est `{"users": [{"uuid": …}]}` — des **uuid** d'utilisateur, d'où
  `remote_user_uuid` sur `wazo.user`. `remote_user_id` (l'identifiant d'URL)
  ne conviendrait pas.
* L'appel **remplace l'ensemble** des membres : le contrat le dit noir sur blanc
  (« This endpoint remove all members which are not defined »). La liste envoyée
  doit donc toujours être complète, jamais un delta.
* **Il n'existe aucun `GET`** sur ce chemin : le contrat ne déclare que des
  `PUT` (et un `PUT` jumeau pour des membres « extensions »). La composition d'un
  groupe ne se relit donc **pas** par l'API. Conséquence assumée : la preuve
  programmatique s'arrête au `204` du `PUT` ; la vérification de bout en bout
  passe par un appel au numéro du groupe, qui doit faire sonner les postes.
* `priority` n'est utilisé que par la stratégie `linear`, et Odoo ne l'envoie
  pas : **l'ordre des membres n'est pas réglable depuis Odoo**. Les sept
  stratégies restent choisissables — six n'ont pas besoin de priorité —, mais
  `linear` sonnera dans un ordre non maîtrisé tant que ce volet n'est pas fait.

### Vérification en direct

| Preuve | Résultat |
|---|---|
| Groupe créé depuis Odoo (poste `2002`, 1 membre) | `action_sync_wazo` → `True`, état `synced` |
| Relecture du PBX | `label` « Groupe QA P4.3 », `ring_strategy` `all`, `user_timeout` 15, `retry_delay` 5 |
| Relation poste → groupe | l'extension `2002` porte le groupe `ee34ac46-…` |
| Plages libres des groupes | `2002-2099` **avant** → `2003-2099` **après** |

Le dernier point est la preuve la plus parlante : le PBX ne propose plus `2002`
comme libre, parce qu'il est désormais attribué au groupe. La disponibilité est
calculée par le PBX, jamais par le module.

### L'uuid des utilisateurs déjà synchronisés (P4.3b — corrigé)

`remote_user_uuid` est arrivé avec P4.3. Un utilisateur synchronisé **avant**
portait un uuid vide, et comme son état est `synced`, `action_sync_wazo` refuse
de le resynchroniser (« déjà synchronisé ») : il ne pouvait donc **jamais**
devenir membre d'un groupe. Constaté sur le tenant `test` — l'unique utilisateur
(`Odoo Live Test`, poste 1005) était exactement dans ce cas, et l'uuid avait dû
être complété à la main pour la première vérification live. Après une mise à
jour, **tous** les utilisateurs déjà synchronisés sont dans cet état.

`wazo.user._ensure_remote_user_uuid()` relit l'uuid du PBX
(`GET /lines/{id}` → `users[0].uuid`), le stocke, et **ne recrée rien**. La
synchro d'un groupe l'appelle pour chacun de ses membres : un groupe se crée donc
sans intervention, même avec des utilisateurs de l'ancienne génération. Aucun
appel n'est fait quand l'uuid est déjà connu, ni pour une fiche jamais
synchronisée (il n'y aurait rien à relire).

### Le libellé : un motif imposé par Wazo (P4.3c)

Wazo valide le libellé d'un groupe **avant** de l'accepter :

```python
# The label is going to end in queues.conf and used in agi.verbose calls.
LABEL_REGEX = r'^[-_.a-zA-Z0-9 ]+$'
label = fields.String(validate=[Length(max=128), Regexp(LABEL_REGEX)], required=True)
```

Autrement dit : lettres **non accentuées**, chiffres, espaces, `-` `_` `.`, et
128 caractères au plus. Les accents sont exclus — pour un déploiement
francophone, ce n'est pas anecdotique : « Réception » est refusé.

L'échec s'était produit **en pleine synchronisation** (`POST /groups` → HTTP 400,
`label: ['String does not match expected pattern.']`), le groupe restant en état
`error`. Le contrôle est donc désormais **local** (`_check_name_is_a_wazo_label`) :
le refus arrive à la saisie, avec un message qui dit quels caractères sont
acceptés et pourquoi. Vérifié en direct : `Réception (accueil)` est refusé sans
aucun appel à l'API.

### Un échec en cours de séquence (P4.3d)

La séquence fait quatre appels : un échec au deuxième laisse le premier abouti.
Or l'uuid du groupe n'était consigné qu'à la toute fin, en cas de succès : une
panne au milieu créait un groupe au PBX **sans trace dans Odoo**, donc
impossible à nettoyer depuis Odoo — le cas exact que P4.2b cherchait à éviter
pour les postes.

Les identifiants sont maintenant écrits **dès qu'ils sont obtenus** :
`remote_group_id` juste après `POST /groups`, `remote_extension_id` juste après
`POST /extensions`. Le RED l'a montré sans ambiguïté — `False != 'grp-uuid-3'` —
et la suppression nettoie alors ce qui a réellement été créé. Le même soin est
appliqué au chemin de reprise.

## 10. Inventaire du contexte (P4.4)

Tout ce qui précède contrôle ce que le module **écrit**. L'inventaire regarde
l'autre moitié : ce qui **existe déjà** sur le contexte, y compris sans fiche
Odoo. C'est la seule vue qui montre les numéros occupés par personne — et ils
comptent : le PBX les compte comme **pris**, donc un numéro orphelin est un
numéro qu'on ne peut plus attribuer.

Le modèle (`wazo.extension.inventory`) est **transitoire** : chaque chargement
jette ses lignes et les reconstruit depuis le PBX. Rien n'est conservé en base,
donc rien ne peut diverger du réel — le raisonnement appliqué aux plages (§1)
vaut ici aussi. Conséquence assumée : la vue est vide à l'ouverture, d'où le
bouton **Rafraîchir depuis Wazo** et son écran d'accueil.

| Colonne | Ce qu'elle dit |
|---|---|
| Poste | le numéro, tel que le PBX l'écrit (donc en texte) |
| Rattaché à | utilisateur, groupe, file, conférence, renvoi, parc — ou **Aucun** |
| Détail | le nom de la ressource qui l'occupe |
| Orpheline | aucun rattachement, coché |
| Dans une plage | le numéro tombe dans une plage déclarée, tous types confondus |
| Fiche Odoo | la fiche Odoo qui le tient (`wazo.user, …` / `wazo.ring.group, …`) |

Deux populations se lisent d'un coup d'œil, et les couleurs les distinguent :

* **en rouge** — orpheline **et hors de toute plage** : une épave, à supprimer
  dans Wazo (le cas `5101`) ;
* **en orange** — orpheline **mais dans une plage** : un numéro rendu
  indisponible sans raison (le cas `2001`).

Les postes tenus par une fiche Odoo sont ceux qui ne posent pas question ; c'est
la colonne « Fiche Odoo » qui les sort du doute, et le filtre **Sans fiche
Odoo** qui les écarte.

### Relevé réel, sur le tenant `test`

| Poste | Rattaché à | Détail | Fiche Odoo | Plage |
|---|---|---|---|---|
| `1001`–`1004` | utilisateur | Test User1 … Test User4 | — | oui |
| `1005` | utilisateur | Odoo Live Test | `wazo.user` | oui |
| `1011` | utilisateur | PoC Multi PoC | — | oui |
| `2000` | groupe | `grp-test-0c33834d-…` | — | oui |
| `2001` | **aucun** | — | — | oui |
| `2002` | groupe | `grp-test-ee34ac46-…` | `wazo.ring.group` | oui |
| `5101` | **aucun** | — | — | **non** |

Soit 10 postes, **2 orphelines** (une dans une plage, une en dehors) et 2 postes
tenus par Odoo — dont le groupe créé au §9, ce qui referme la boucle : ce que le
module crée, l'inventaire le retrouve.

Un appel par inventaire, plus un pour les propriétaires **seulement si** un poste
a une ligne, plus un pour les plages déclarées : `GET /extensions`,
`GET /contexts`, `GET /contexts/{id}`, `GET /users`. La table des propriétaires
est partagée avec le contrôle des postes (`_line_owners`) plutôt que réécrite.

## 11. Priorité de sonnerie des membres (P4.5)

La stratégie « un après l'autre » n'a de sens que si l'ordre est réglable — or
il ne l'était pas : le lien membre était un ``Many2many``, incapable de porter
une donnée. La priorité est donc passée **sur le lien**, ce qui en fait un
modèle (`wazo.ring.group.member`) : `group_id`, `user_id`, `priority` (défaut
10, pas de 10) et un contrôle d'unicité — un même utilisateur ne sonne pas deux
fois dans un groupe, ce que la table relationnelle garantissait implicitement
par sa clé primaire. La vue porte toujours le poste et l'état de l'utilisateur
(champs liés), donc rien n'a été perdu au passage.

La charge utile envoyée à Wazo est **triée par priorité** : c'est cet ordre que
le PBX suit, la plus petite priorité sonnant d'abord. Seul l'ordre compte — les
écarts ne veulent rien dire, d'où des pas de 10 qui laissent de la place pour
insérer.

**Reprise des données** (`migrations/19.5.3/post-migrate.py`) : sans elle, les
groupes déjà synchronisés perdaient leurs membres côté Odoo alors que le PBX
les garde — et la synchronisation suivante les aurait effacés **là-bas aussi**,
l'appel des membres remplaçant l'ensemble. Les liens existants sont recopiés à
la priorité par défaut (aucun historique à reconstituer). L'ancienne table est
**laissée en place** : inerte, elle sert de donnée de retour arrière.

**Deux pièges, tous deux silencieux**, valent d'être retenus car ils ne
produisent ni erreur ni test rouge :

* le répertoire de migration doit s'appeler `19.5.3` — forme **courte** — et
  non `19.5.3.0.0` : Odoo 20 refuse la forme longue (`Invalid version for
  upgrade script`) et préfixe toute forme courte par la version du serveur.
  Tant que le manifeste déclarait `19.5.3.0.0`, **aucun script de migration
  n'était exécutable** dans ce module. La version du manifeste est donc passée
  à `19.5.3`, la forme courte qu'utilisent les modules d'Odoo eux-mêmes ;
* la reprise est en `post-migrate`, car la table d'arrivée n'existe qu'une fois
  le modèle mis à jour.

**Vérifié en direct** : la charge utile
`{'users': [{'uuid': 'bea676a0-…', 'priority': 30}]}` est acceptée par Wazo,
puis **relue du PBX** — `GET /groups/{uuid}` renvoie
`members.users[].priority = 30`. La priorité est donc bien stockée côté Wazo, et
la remise à 10 referme l'état sur celui de la reprise. À noter pour la suite :
c'est `GET /groups/{uuid}` qui expose les membres (la sous-ressource
`/groups/{uuid}/members/users`, elle, n'accepte que `PUT` — le 405 qui avait
égaré la première vérification en P4.3).
