La façade générique de N1 exclut les modèles techniques, et c'est exactement ce
qu'est une page du site : son contenu vit dans l'`arch` d'une vue QWeb, exécutée
côté serveur. Sans module dédié, N1 ne pourrait donc pas toucher au site.
Celui-ci lui ouvre le seul corps éditable (`<div id="wrap">`), jamais la vue.

Le module travaille comme l'éditeur web, avec les droits du demandeur :
`ir.ui.view.save` pour l'écriture, `website.new_page` pour une page neuve,
`theme.utils` pour un thème. Trois garde-fous non évidents : l'HTML reçu est
assaini avant écriture (balises QWeb, `script`, formulaire, iframe, `svg`,
attributs `t-*`, `on…`, métadonnées `data-oe-*` qui lieraient un élément au
champ d'un autre enregistrement) ; une empreinte SHA-256 lue au préalable évite
d'écraser une modification concurrente ; et une page qui contient déjà du QWeb
ou un élément que l'assainissement supprimerait est refusée, renvoyée à
l'éditeur web.

L'ensemble est tracé dans `hermes.n1.change`, avec le HTML d'avant et d'après, et
rejouable sans effet de bord. Une page créée reste non publiée : un humain la
relit et la publie. Le catalogue de blocs (`lister_blocs_web`, `lire_bloc_web`)
permet de composer comme dans l'éditeur, sans exposer les blocs dynamiques. Le
demandeur doit être administrateur en conversation privée avec N1 et membre de
`website.group_website_designer`.
