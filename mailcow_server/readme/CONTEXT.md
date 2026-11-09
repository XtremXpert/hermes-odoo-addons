L'exploitant de la plateforme (xtremxpert.ca) doit pouvoir entretenir l'instance
Mailcow elle-même — état du serveur, version, relais SMTP, quarantaine globale —
alors qu'un exploitant de tenant (diverse-cite.com, …) n'administre que ses
domaines, boîtes et alias. Les deux métiers ne se recouvrent pas : un tenant n'a
rien à faire dans les outils d'entretien du serveur, et l'exploitant de la
plateforme n'a pas à porter les écrans d'exploitation d'un client. D'où deux
couches : `mailcow_tenant` pour le tenant, `mailcow_server` pour la plateforme.

Le module est pour l'instant une **coquille** : son seul code est un
`__init__.py` vide, et son manifeste ne déclare ni modèle, ni vue, ni donnée, ni
règle d'accès. Il existe pour poser la frontière et la dépendance : il dépend de
`mailcow_tenant` et n'ajoutera ses outils d'entretien que plus tard, sans que les
instances de tenants aient à l'installer. Son installation est donc sans effet
visible.

Les modules voisins précisent la répartition : `mailcow_tenant` porte
l'exploitation d'un serveur (domaines, boîtes, alias, client API, réglages de
connexion), `mailcow` porte les écrans d'ensemble côté usager, et
`mailcow_server` restera l'outillage de l'exploitant de la plateforme. Il ne
s'installe que sur l'Odoo qui administre le serveur Mailcow, jamais sur celui
d'un tenant.
