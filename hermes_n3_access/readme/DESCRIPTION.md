Crée le compte Odoo de l'agent d'infrastructure **Hermes N3** et le désactive sur les copies neutralisées de la base.

- L'installation crée l'utilisateur **Hermes N3 Infrastructure**, identifiant `hermes_n3`. C'est un utilisateur interne avec le groupe de gestion des contacts, jamais administrateur.
- Le compte n'a pas de mot de passe et aucun courriel de réinitialisation n'est envoyé : il ne sert pas aux connexions interactives.
- L'agent passe par l'API JSON-2, avec une clé API créée par un humain sur la fiche de l'utilisateur. Le module ne crée aucune clé.
- À la neutralisation d'une base (par exemple une copie de production restaurée en staging), `data/neutralize.sql` supprime les clés API du compte `hermes_n3`, puisqu'elles sont valables sur la production, puis désactive le compte. Les autres utilisateurs et leurs clés ne sont pas touchés.
