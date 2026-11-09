Ce module n'a pas d'impact sur l'interface utilisateur.

Rien à faire après l'installation : sur une base neutralisée (paramètre
`database.is_neutralized` posé par `odoo neutralize`), le planificateur, le bouton
_Exécuter manuellement_ des tâches planifiées et les appels programmatiques sont
refusés et journalisés. Sur une base normale, le garde-fou est transparent.
