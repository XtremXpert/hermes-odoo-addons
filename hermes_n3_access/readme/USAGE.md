Ce module n'a pas d'impact sur l'interface utilisateur : il ne pose ni menu ni vue.

L'installation crée le compte **Hermes N3 Infrastructure** (identifiant `hermes_n3`),
visible dans _Réglages_ > _Utilisateurs & Sociétés_ > _Utilisateurs_. Ce compte n'a
pas de mot de passe et ne sert pas aux connexions interactives : l'agent passe par
l'API JSON-2 avec une clé API créée par un humain (voir Configuration).

Sur une copie neutralisée de la base, les clés API du compte sont supprimées et le
compte est désactivé ; rien à faire après une resynchronisation.
