# La forme d'une version décide si une migration tourne

Constaté en écrivant les scripts de migration de `wazo_phone`, puis vérifié de
bout en bout sur un module jetable. Le sujet n'est pas la version du manifeste :
c'est **le nom du dossier** sous `migrations/`.

## Ce que fait Odoo

`odoo/odoo/modules/migration.py` tient `VERSION_RE`, un motif **ancré** (`^…$`),
que son propre commentaire résume :

> After Odoo version we allow precisely 2 or 3 parts

Un nom de dossier acceptable s'écrit donc `19.5.3`, `19.5.2.1` — deux ou trois
nombres après un préfixe de forme `x.0`. `19.5.3.0.0` n'en est pas un.

## Les trois expériences

Module jetable `zz_essai_segments` (git-ignoré, effacé après), manifeste et
dossier de migration accordés de trois façons :

| Manifeste | Dossier | Ce qui se passe |
|---|---|---|
| `19.5.2.0.0` | `migrations/19.5.2.0.0/` | **avertissement** `Invalid version for upgrade script`, `migrate()` jamais appelé |
| `19.5.3.0.0` | `migrations/19.5.3/` | dossier **accepté**, `migrate()` appelé **0 fois**, **aucun avertissement** |
| `19.5.4` | `migrations/19.5.4/` | la migration tourne : `post from 19.5.3.0.0 to 19.5.4 in 0.001 seconds` |

La deuxième ligne est la dangereuse : la migration est **silencieusement inerte**.
Rien dans le journal ne le dit, et la version en base avance quand même. La
troisième est le remède : la **forme courte** du manifeste, qui rend le dossier
nommable.

## Ce que ce dépôt en fait

- `tools/verifier_les_restes.py` refuse un module qui **porte** des scripts de
  migration sans pouvoir les nommer. Il accepte `19.5`, `19.5.3` et `19.5.2.0.0`
  comme formes de manifeste : les trois sont valides.
- `mailcow_admin` (`19.5.2.0.0`) et `voipms_sms` (`19.5.1.0.0`) sont en cinq
  segments et n'ont **aucun** script de migration : sans risque aujourd'hui. Le
  jour où l'un recevra une migration, sa version devra passer en forme courte —
  c'est écrit ici pour que ce jour-là ne coûte pas une seconde enquête.
