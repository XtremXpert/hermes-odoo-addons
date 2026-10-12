Gestion des instances Odoo d'un cluster Kubernetes (ressources `OdooInstance` de
l'opérateur Bemade) depuis Odoo : instances de production et de staging, images,
sauvegardes, restaurations, mises à jour de modules (`k8s.odoo.upgrade`) et
resynchronisation d'un staging, y compris depuis un autre cluster.

C'est le socle du portail `odoo_herd_portal`, qui y ajoute la barrière humaine des mises
en production (promotion confirmée par code) et les façades des agents.

Module d'origine : Bemade Inc. (`bemade/bemade-addons`), porté en 20.0 et maintenu par
Diverse-Cité.
