L'agent d'infrastructure N3 a besoin d'un compte Odoo pour appeler l'API
JSON-2, mais ce compte ne doit jamais être administrateur ni servir à une
connexion interactive. Ce module ne crée que cela : un utilisateur interne, ses
groupes minimaux et sa neutralisation sur les copies. La façade et les outils N3
vivent ailleurs (broker Hermes), d'où la séparation.

Le compte est un enregistrement XML (`data/res_users.xml`) : nom « Hermes N3
Infrastructure », identifiant `hermes_n3`, groupes `base.group_user` et
`base.group_partner_manager`, sans mot de passe et avec `no_reset_password` —
aucun courriel de réinitialisation n'est envoyé. Le module ne crée aucune clé
API : elle est créée par un humain sur la fiche utilisateur, ce qui garde le
secret hors du dépôt et du code.

À la neutralisation d'une base, `data/neutralize.sql` supprime les clés API du
compte puis le désactive, sans toucher aux autres utilisateurs. C'est la
contrepartie de l'API : un staging restauré depuis la production ne doit jamais
pouvoir être piloté par l'agent. Le module est caché : ni menu, ni vue, ni
réglage.
