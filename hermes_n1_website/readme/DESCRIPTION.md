Permet à Hermes N1 de lire et de réécrire le **corps** d'une page du site web (la zone `<div id="wrap">`), à la demande d'un administrateur, avec le même contrôle de version et la même trace que ses autres corrections. La vue QWeb de la page n'est jamais écrite directement.

## Fonctionnement

- `hermes.n1.change.lire_page_web(page_id, …)` renvoie le HTML effectif de `#wrap` (héritages du site compris), son empreinte SHA-256 et, le cas échéant, la raison pour laquelle la page n'est pas modifiable par N1.
- `modifier_page_web(page_id, html, expected_sha256, reason, …)` :
  - refuse si la page a changé depuis la lecture (empreinte différente) ;
  - refuse si la zone actuelle contient du QWeb ou un élément que l'assainissement supprimerait (formulaire, iframe, script, svg…) : ces pages se modifient dans l'éditeur web ;
  - assainit le HTML reçu : balises QWeb, `script`, `iframe`, `form`, champs de saisie, attributs `t-*`, `on…`, `data-oe-*` (métadonnées de l'éditeur qui permettraient d'écrire d'autres enregistrements) et liens `javascript:`/`data:` retirés ;
  - enregistre par `ir.ui.view.save`, comme l'éditeur web, avec les droits du demandeur (`website.group_website_designer` requis) et dans le contexte du site de la page ;
  - consigne l'opération dans `hermes.n1.change` avec le HTML d'avant et d'après (retour arrière possible) et une note.

## Nouvelle page

`creer_page_web(website_id, name, html, reason, …, add_menu=False)` crée une page comme « Nouvelle page » dans l'éditeur web (`website.new_page`, modèle de page vierge), puis remplit sa zone `#wrap` avec le même assainissement que `modifier_page_web`. La façade générique ne peut pas créer de `website.page`, dont la vue QWeb est un objet technique.

- L'adresse vient du nom (« Ente Auth » donne `/ente-auth`) ; si une page ou une adresse existe déjà, la création est refusée : la page existante se lit avec `lire_page_web` et se modifie avec `modifier_page_web`. Rien n'est jamais écrasé ni dupliqué.
- La page est créée **non publiée** : un humain la relit et la publie depuis l'éditeur web.
- `add_menu=True` ajoute une entrée au menu principal du site.
- Exige `website.group_website_designer` et le droit d'écrire sur le site ; s'exécute avec les droits du demandeur et dans le contexte du site.
- Consigné dans `hermes.n1.change` (avant vide, après : adresse, nom, menu, HTML), avec une note. Une demande rejouée ne crée pas de seconde page.

## Blocs Odoo

Pour composer une page comme dans l'éditeur web, N1 utilise les blocs d'Odoo :

- `lister_blocs_web(offset)` liste les blocs statiques du site (`website.s_*`), sans les sous-éléments, fenêtres surgissantes et blocs dynamiques (formulaires, cartes, listes d'articles ou de produits…) ;
- `lire_bloc_web(key)` renvoie le HTML du bloc **rendu par Odoo**, avec `data-snippet` et `data-name` comme l'éditeur l'insère. Un bloc qui contiendrait des éléments dynamiques est refusé.

L'assainissement conserve le balisage des blocs (classes `s_*`, `data-snippet`, `data-name`, attributs Bootstrap, options comme `data-oe-shape-data`) ; seules les métadonnées qui lient un élément au champ d'un autre enregistrement (`data-oe-model`, `-id`, `-field`, `-xpath`, `-expression`, `-type`…) sont retirées.

Le demandeur doit être un administrateur en conversation privée avec N1 (règles de `hermes_n1_audit`). Une demande rejouée ne réécrit pas la page.

## Thème d'un nouveau site

`appliquer_theme_web(website_id, theme, reason, …)` charge un thème **déjà installé** (`theme_*`) sur un site qui n'a pas encore de thème, avec les mêmes étapes que le bouton « Choisir ce thème » d'Odoo, pour ce site seulement :

- n'installe ni ne met à jour aucun module : l'installation d'un thème relève de N3 ;
- refuse un site qui a déjà un thème, car le remplacer retirerait du site les enregistrements du thème et leurs personnalisations : ce changement se fait dans l'éditeur web ;
- exige `website.group_website_designer` pour le demandeur et le droit d'écrire sur le site ;
- consigne l'opération dans `hermes.n1.change`, avec une note. Une demande rejouée ne recharge pas le thème.

## Dépendances et tests

Dépend de `hermes_n1_audit` et `website`.

```sh
ADDONS=addons tools/test-modules.sh IMAGE hermes_n1_website
```

Les tests couvrent la création d'une page (non publiée, assainie, tracée, jamais en double), la lecture et l'écriture du seul `#wrap` avec trace et rejeu, l'assainissement, le refus d'une empreinte périmée, d'une page à QWeb ou à formulaire.
