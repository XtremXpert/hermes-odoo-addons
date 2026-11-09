Ce module n'a pas d'impact sur l'interface utilisateur : il n'ajoute ni menu ni vue.
N1 lit et réécrit la zone `<div id="wrap">` des pages du site par RPC, avec les droits
du demandeur et la trace de ses autres corrections.

Une page créée par N1 reste non publiée : un humain la relit et la publie depuis
l'éditeur web. Une page ou une adresse déjà existante n'est jamais écrasée ni
dupliquée : elle se lit puis se modifie. Les pages qui contiennent du QWeb ou un
élément que l'assainissement supprimerait (formulaire, iframe, script, svg…) se
modifient dans l'éditeur web, pas par N1.
