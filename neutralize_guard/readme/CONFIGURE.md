Aucun réglage propre : le module n'expose ni `res.config.settings`, ni paramètre
système, ni groupe de sécurité. Il ne lit qu'un paramètre du cœur d'Odoo,
`database.is_neutralized`, posé par `odoo neutralize`, et n'ajoute ni menu, ni
règle d'accès. Rien à configurer : sur une base neutralisée, le garde-fou refuse
les crons ; sur une base normale, il est transparent.
