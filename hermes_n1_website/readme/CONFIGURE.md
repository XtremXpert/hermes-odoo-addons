Aucun réglage propre, vérifié dans le module : il n'expose ni
`res.config.settings`, ni paramètre système, ni groupe, et son manifeste ne
charge aucun fichier `data`.

Les droits sont ceux des modules voisins : le demandeur doit être membre de
`hermes_n1_audit.group_agent` (pour la façade) et de
`website.group_website_designer` (pour écrire sur le site), et l'agent doit
écrire sur le site visé. Si l'un de ces droits manque, l'appel est refusé
(`AccessError`) ; il n'y a donc rien à régler ici, seulement des groupes à
attribuer dans `hermes_n1_audit` et `website`.
