# Dépôt, tests et conventions

## Où vit ce module

Il est versionné dans le dépôt **`hermes-odoo-addons`** (GitHub `XtremXpert`),
dont la racine sert aussi de clone de travail Odoo 20. Les sources d'Odoo
(`odoo/`, `enterprise/`, `design-themes/`, `industry/`) et la configuration
locale (`conf/`) sont **ignorées** par git : ce dépôt ne contient que des
modules. Branche `main`, commits directs, pas de CI — les addons précédents
(`asterisk_ari`, `voipms_sms`, `mailcow_admin`) ont été ajoutés de la même
façon, en un commit.

## Lancer les tests

Toute la suite, depuis la racine du clone :

```bash
PYTHONPATH="" .venv/bin/python odoo/odoo-bin -c conf/odoo.conf \
    --database odoo20 -u wazo_phone --test-tags wazo_phone \
    --stop-after-init --log-level=test
```

Une seule classe : `--test-tags "/wazo_phone:TestRingGroupSync"`. Les échecs se
lisent avec `grep -E "FAIL: |ERROR: |failed, "` sur la sortie.

Les vérifications contre le **vrai PBX** passent par le shell d'Odoo :

```bash
PYTHONPATH="" .venv/bin/python odoo/odoo-bin shell -c conf/odoo.conf \
    --database odoo20 --no-http < /tmp/sonde.py
```

`timeout` **n'existe pas** sur macOS : ne pas l'utiliser dans un script. Une
sonde qui écrit au PBX doit valider sa transaction locale (`env.cr.commit()`),
sinon le PBX garde des ressources sans trace côté Odoo.

## Ce qui n'est pas versionné, et pourquoi

`poc/` (scripts d'exploration jetables) est exclu par le `.gitignore` du
dépôt : ces fichiers portent des identifiants de la VM de test — dont un mot de
passe de poste en clair, et un digest MD5 dérivé de ce mot de passe. Le savoir
utile a été reporté dans `doc/` (et dans le skill `wazo-operations`).

**Avant tout commit qui ajoute des fichiers jusque-là non suivis**, vérifier ce
point : `git diff --cached` puis rechercher les valeurs ressemblant à des
identifiants. Les seules chaînes de ce genre qui restent dans le module sont
des **fixtures de test** (`reg_secret_1011`, `secret_7000`, `other-token`),
inventées, sans valeur d'authentification.

## Versions et migrations

La version du manifeste est en forme **courte** (`19.5.3`), comme celle des
modules d'Odoo eux-mêmes. Ce n'est pas cosmétique : Odoo 20 refuse un
répertoire de migration à plus de trois segments (`Invalid version for upgrade
script`) et préfixe toute forme courte par la version du serveur — si bien
qu'une version longue du type `19.5.3.0.0` rend `migrations/` **totalement
inopérant**, sans erreur ni test rouge. Les scripts de reprise s'appellent donc
`migrations/19.5.3/post-migrate.py`.

Un script de reprise s'exécute **après** la mise à jour du modèle s'il touche
une table créée par celle-ci (`post-migrate`), et **avant** dans le cas
contraire (`pre-migrate`). Vérifier l'effet réel (nombre de lignes, ligne de
journal), jamais le code de sortie : une migration qui ne copie rien sort en 0.
