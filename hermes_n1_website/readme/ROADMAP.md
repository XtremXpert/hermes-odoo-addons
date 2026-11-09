Seule la zone `<div id="wrap">` est accessible. Une page qui n'en a pas
exactement une est refusée, et une page qui contient du QWeb ou un élément que
l'assainissement supprimerait (formulaire, iframe, script, svg…) doit être
modifiée dans l'éditeur web.

`lire_bloc_web` rend les blocs avec le premier site par identifiant
(`search([], order="id", limit=1)`) : en multi-site, le rendu d'un bloc peut donc
dépendre d'un autre site que celui de la page visée. Les blocs marqués
dynamiques ou composés ne sont pas proposés au catalogue.

Le thème ne s'applique qu'à un site qui n'a encore aucun thème, et seulement
depuis un module `theme_*` déjà installé : ce module n'installe ni ne met à jour
aucun module. Remplacer un thème existant se fait dans l'éditeur web.

Une page créée reste non publiée et son adresse vient du nom ; une adresse déjà
prise est refusée. Le HTML reçu est limité à 200 000 caractères.
