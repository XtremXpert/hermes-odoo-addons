# hermes-odoo-addons

Treize modules Odoo maison pour l'infrastructure de Diverse-Cité : courriel (Mailcow),
téléphonie (Wazo, Asterisk ARI), SMS (VoIP.ms), le socle commun des agents Hermes
(compte N3, journal N1, activité Discuss, pages web N1, SSO des tableaux de bord), et la
gestion des instances Odoo du cluster avec sa barrière humaine des mises en production
(odoo_herd, odoo_herd_portal), plus un correctif de l'écran Applications
(base_module_type_official). Dépôt **public** depuis le 2026-10-11 (diverse-odoo et
mac-demo le vendorisent sans jeton) : rien de secret n'y entre, ni dans un fichier ni
dans l'historique.

Le local se monte avec `odoo-dev setup --no-docker --yes`, après `cp .env.exemple .env`
; le lancement passe par `./start.sh`, jamais `odoo-bin` à la main. `.deploy/` est un
sous-module (`XtremXpert/odoo-deploy`, branche 19.0) qui porte le déploiement — il n'est
pas nécessaire au développement local.

| module                      | rôle                                         |
| --------------------------- | -------------------------------------------- |
| `mailcow_server`            | plateforme : entretien du serveur Mailcow   |
| `mailcow_tenant`            | tenant : domaines, boîtes, alias, synchro    |
| `mailcow`                   | côté usager : vue d'ensemble du serveur      |
| `wazo_server`               | plateforme : création et cycle des tenants   |
| `wazo_tenant`               | tenant : usagers, postes, groupes, CDR       |
| `wazo_phone`                | téléphone dans Odoo (WebRTC, click-to-call)  |
| `wazo_voipms`               | pont VoIP.ms : trunk sortant, DIDs entrants  |
| `asterisk_ari`              | Asterisk via ARI                             |
| `voipms_sms`                | SMS par l'API VoIP.ms                        |
| `hermes_n3_access`          | compte API de l'agent Hermes N3              |
| `hermes_n1_audit`           | façade d'écriture N1 et journal immuable     |
| `hermes_activity`           | réponses et activité des agents dans Discuss |
| `hermes_n1_website`         | pages web du site par N1 (zone #wrap)        |
| `hermes_dashboard_sso`      | SSO OAuth2 des tableaux de bord Hermes       |
| `odoo_herd`                 | instances Odoo du cluster (opérateur Bemade) |
| `odoo_herd_portal`          | portail, promotions confirmées, façades      |
| `base_module_type_official` | modules visibles dans Applications           |

Le dépôt suit la **disposition des dépôts de modules de l'OCA** (gabarit
`oca-addons-repo-template`, `.copier-answers.yml`) : chaque module est **à la racine**,
avec son `pyproject.toml`, son `readme/` et le `README.rst` qui en est généré, et
`pre-commit` applique les contrôles de l'OCA. La racine du dépôt est donc le chemin
d'addons. C'est ce qui permet à un projet (maison) de vendoriser un module tel quel :
`odoo-dev vendor add <module> --source …` n'extrait qu'un module placé à la racine. Les
clones externes (`odoo/`, `enterprise/`, `design-themes/`, `industry/`) restent à la
racine, git-ignorés. `tools/test` et la CI suivent cette disposition : leur
`--addons-path` pointe sur la racine (`.`), et le lint porte sur tout le dépôt (ruff
respecte `.gitignore`, donc ignore ces clones).

`AGENTS.md` dit comment travailler ici ; **`docs/` garde ce qui a été mesuré** — une
expérience, son résultat, la règle qu'on en tire. Une note n'y entre que si elle porte
une mesure.

## La série est 20.0 — et la version suit la forme longue de l'OCA

Les modules suivent la série **20.0**, en forme longue : `'version': '20.0.x.y.z'`.
C'est la forme qu'exige `pylint-odoo` (`manifest-version-format`) et elle est sans effet
sur une base déjà installée : Odoo juge `20.0.3` égal à `20.0.3.0.0` (mesuré), donc
passer de l'une à l'autre ne déclenche aucune mise à jour. Avant de choisir un
identifiant d'API, vérifier la série — les ruptures connues sont consignées dans la
skill `odoo20-breaking-changes`.

La version d'un module qui porte un script de migration doit tenir dans un **nom de
dossier** : Odoo n'accepte, après un éventuel préfixe de série (`20.0.`), que **deux ou
trois nombres** — `20.0.3.0.0`, `19.0.1.2.3`, `2.0`. En 20.0, la forme longue est donc
nommable : `migrations/20.0.3.0.0/` est un dossier valide (mesuré). Les deux échecs
possibles ne se ressemblent pas, et le second est le pire : un dossier refusé laisse un
`Invalid version for upgrade script` dans le journal ; un dossier accepté qui ne
correspond pas à la version courante **ne dit rien et n'exécute rien**.

La règle de la « forme courte » venait de la série **19.5** (l'arbre `master` d'Odoo,
qui se déclarait `19.5.0 alpha`) : `19.5.` n'est pas un préfixe de série, et un
manifeste à cinq segments (`19.5.2.0.0`) n'y était nommé par aucun dossier. Mesuré alors
sur un module jetable : installé en `19.5.1.0.0`, mis à jour en `19.5.3.0.0` avec un
script dans `migrations/19.5.3/` — aucun avertissement, aucune ligne, `migrate()` jamais
appelé. Passé à la forme courte `19.5.4` avec `migrations/19.5.4/` :
`post from 19.5.3.0.0 to 19.5.4`.

`wazo_phone` est le seul module à porter un dossier `migrations/` : la reprise des
membres de groupes d'appel (P4.5), d'abord nommée `19.5.3/`. En 20.0, ce nom ne
s'exécutait plus : sans préfixe de série, Odoo lisait `19.5.3` comme une version **du
module** (`20.0.19.5.3`), au-delà de la version courante. Le dossier est renommé
`20.0.3.0.0/` : il s'exécute pour une base encore sous une version antérieure (série
19.5), et pas pour une base déjà en `20.0.3` (Odoo juge `20.0.3` == `20.0.3.0.0`). Le
script est protégé (rien si l'ancienne table manque) et idempotent. Une prochaine
migration se nomme en forme longue, `migrations/20.0.x.y.z/`.
`tools/verifier_les_restes.py` refuse toute version hors série.

## Branche

`main` uniquement, poussée directement. **Aucun commit ne part sans une CI verte** :
rejouer les commandes de la CI localement (plus bas) avant de pousser. Ne jamais amender
un commit déjà poussé, même en étant le seul committeur.

## Disposition

- **les dix modules, à la racine** — la racine est aussi, littéralement, un chemin
  d'addons, ce qui permet de les atteindre sans les déplacer ;
- `odoo/`, `enterprise/`, `design-themes/` — **clones simples, git-ignorés, pas des
  sous-modules** :
  - `odoo/` et `design-themes/` sont **publics** (`github.com/odoo/odoo`,
    `github.com/odoo/design-themes`) : clonables sans identifiant ;
  - `enterprise/` est **privé et sous licence** : il reste sur le disque, **délibérément
    hors du chemin d'addons**. Odoo répond `None` à `get_module_path('web_studio')`. Ne
    pas le supprimer, ne pas l'ajouter au chemin — et ne pas s'étonner de voir ses
    modules dans la liste des applications : ils viennent du catalogue
    `base/data/ir_module_module.xml` (`to_buy`, licence `OEEL-1`), présent sur toute
    base, y compris neuve ;
- `conf/odoo.conf` — configuration locale, git-ignorée ;
- `start.sh` — **le seul lanceur autorisé** ;
- `.github/workflows/ci.yml` et `.github/scripts/verifier_les_xml.py` — la CI et son
  validateur ;
- `ruff.toml` — chaque exception porte sa raison ;
- `tools/` — les outils du dépôt : `test`, `verifier_les_restes.py`,
  `modules_fantomes.py`, `odoo_lock.py`, et le crochet `hooks/pre-commit` ;
- `odoo.lock` — la révision d'Odoo (et des thèmes, et d'entreprise) contre laquelle le
  dépôt a été éprouvé : `tools/odoo_lock.py write|check` ;
- `logs/` — journaux des exécutions locales, ignorés par git ;
- `poc/` — jetons et mot de passe d'une VM de test : **exclu**, jamais committé.

## Chemin d'addons complet

Dans cet ordre, tel que `conf/odoo.conf` le déclare (en absolu sur ce poste) :

```
odoo/addons,odoo/odoo/addons,design-themes,.
```

`design-themes` y est parce que les thèmes de site en dépendent ; `enterprise` n'y est
pas, par choix.

## Lancer

```bash
./start.sh                                # le serveur : 2069 (et 2072 pour le bus)
./start.sh -d odoo20                      # une seule base
./start.sh --workers 2                    # prefork — nécessaire au bus /websocket
./start.sh shell --no-http < sonde.py     # inspection ponctuelle
```

**Jamais `odoo-bin` à la main, même pour une ligne.** Le script pose `PYTHONPATH=""`,
passe `-c conf/odoo.conf` **après** les arguments (sinon `shell` est lu comme un
argument du serveur : `unrecognized parameters: shell`), et sans lui une exécution peut
se figer à 0 % de CPU au lieu de planter. `db_host` est **vide** dans la conf : la
connexion passe par le socket Unix. Y remettre `localhost` fait négocier GSSAPI à libpq,
ce qui traverse XPC — et XPC n'est pas _fork-safe_ : chaque worker forké meurt en
silence.

`dbfilter = ^odoo20` fait que le sélecteur ne propose que `odoo20` et `odoo20_neuve`,
pas les cent trente autres bases du poste. Servir deux bases fait passer `/web/login`
par le sélecteur : c'est normal.

## Tester

```bash
./start.sh -d odoo20 --http-port 2071 --gevent-port 2074 \
  --test-enable --stop-after-init \
  --test-tags=mailcow_admin,wazo_phone,wazo_server,asterisk_ari,voipms_sms \
  > /tmp/suite.log 2>&1
grep 'odoo.tests.result' /tmp/suite.log
```

- **Toujours un `--http-port` explicite** : 2069 est tenu par le serveur de
  développement et Odoo abandonne avant de rien lancer ;
- **jamais `--no-http`** quand on veut les tests navigateur — ils sont alors **sautés en
  silence** et le résultat reste vert. La CI refuse ce saut (voir plus bas) ;
- **`--db-filter` ouvert** dès que la base de test ne commence pas par `odoo20` : le
  filtre de `conf/odoo.conf` ne la couvre pas, le navigateur est renvoyé au sélecteur de
  bases, et le test navigateur échoue sur un élément introuvable — un `303` qu'il faut
  lire dans le journal, aucun message ne l'annonce. `tools/test` s'en charge ;
- juger la ligne `odoo.tests.result`, **jamais le code de sortie d'un tuyau** : un
  `grep` qui ne trouve rien sort en 1, et un journal vide ressemble à un plantage quand
  ce n'est qu'un tampon (préfixer `PYTHONUNBUFFERED=1`) ;
- un test constate un **écart** — lire avant, comparer après. Tout compte absolu est un
  piège : il passe sur la base de développement et casse sur une base neuve.

## Les outils

```bash
tools/test mailcow_admin                # base neuve, ports libres, verdict sur la ligne de résultat
tools/test wazo_phone wazo_server
python3 tools/verifier_les_restes.py    # versions, règles d'accès manquantes, imports JS morts
python3 tools/modules_fantomes.py -d odoo20
python3 tools/odoo_lock.py check        # l'arbre Odoo a-t-il dérivé du verrou ?
```

Et le crochet, qui rejoue tout cela avant chaque commit — à installer une fois :

```bash
git config core.hooksPath tools/hooks
```

Il refuse le commit si une étape échoue : c'est la façon la moins coûteuse de ne plus
jamais pousser un `F841`, un `W292`, une version hors série ou un import JavaScript
mort.

## Vérifier avant de pousser

Ce sont les commandes de la CI, et **rien d'autre** — le lint de l'éditeur n'est pas le
sien (un fichier propre à l'écran peut porter `F841` ou `W292`) :

```bash
python -m pip install --quiet ruff==0.16.9
ruff check . --exclude poc
python -m compileall -q $(git ls-files '*.py')
python .github/scripts/verifier_les_xml.py
node --test '*/static/tests/*.test.js'
python3 tools/test_crochet.py   # le crochet lui-même : il clone, pose une faute, exige le refus
bash tools/test_app_password.sh  # les refus du script de courriel, sans réseau ni secret
python3 tools/verifier_les_restes.py
python3 tools/odoo_lock.py check
```

## Pièges

### Les motifs de chemin dans `ruff.toml` doivent être indépendants de la disposition

Un `per-file-ignores` écrit en dur (`"wazo_server/models/…"`) cesse de correspondre dès
que l'arbre bouge, et la faute qu'il écartait réapparaît **sans que le fichier ait été
touché** — c'est arrivé au déplacement des modules sous `addons/`. Écrire les motifs en
`"**/"`. Même règle pour tout ce qui nomme des chemins : `git ls-files` (donc le
vérificateur XML et le crochet) et `tools/test` suivent, eux, les noms et sont
insensibles au déplacement.

### `.gitignore` : un motif ancré ne suit pas un déplacement

`/wazo_phone/poc/` ne correspond plus après le passage sous `addons/` — et les 22
fichiers qui portent un vrai mot de passe redeviennent visibles pour git au moment
précis où l'on croit avoir tout vérifié. Contrôler avec `git check-ignore -v` **sur un
fichier qui existe** : l'outil compare le motif au texte du chemin et répond « ignoré »
même pour un chemin qui n'existe pas. Et pour compter ce qui entre dans un commit :
`git show --name-only --format="" HEAD`, jamais `--stat`, qui imprime **aussi le
message** et fait croire à des fichiers.

### Ailleurs dans le dépôt

- **OWL 3** : l'état passe par `proxy`, les gabarits qualifient par `this.`, on utilise
  `t-out` (et non `t-esc`), `useEffect`. Un module qui importe `@odoo/owl` doit déclarer
  `web` **et** une directive d'ordre dans ses actifs.
- `-u <module>` **ne régénère pas** les paquets d'actifs : purger `ir.attachment` quand
  un composant change.
- `<button name="x"/>` doit correspondre à une méthode du modèle. Pour obtenir un rouge
  propre, retirer **le modèle et la vue**.
- Dans un `_inherit`, **la première entrée l'emporte**. Étendre un `Selection` demande
  `selection_add` **et** `ondelete`.
- Les imports des `__init__.py` d'un module Odoo ne sont pas morts — un `--fix`
  mécanique casse le registre.
- **Mailcow : lecture seule sur la production.** Les écritures se testent sur un domaine
  jetable, nettoyé aussitôt. Une clé d'API ne passe jamais par la conversation.
- Seuls les tests voient la base de développement **et** la vraie : un `setUpClass`
  visible de toute la classe casse toute garde qui compte globalement.

## Secrets

Le dépôt est public. Ni jeton, ni mot de passe, ni chaîne de connexion dans un fichier
suivi, un commentaire, un message de commit ou une capture. Les filets de restauration
(`/tmp/*.dump`, `/tmp/*.json`) ne sont **jamais** copiés ici.

## Retours prévus

- **`mailcow_tenant`** — le bouton « Créer la boîte Mailcow » sur la fiche usager
  reste visible quand la boîte existe (il lève « La boîte existe déjà »). À faire :
  champ calculé `mailbox_id` pour `invisible`, ou ouvrir l'existante au lieu de
  l'erreur — au choix à l'usage. Pendant ce temps, `wazo_tenant` fait déjà ça bien
  (`invisible="wazo_user_id"`).
