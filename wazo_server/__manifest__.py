# Part of the wazo_server Odoo module. See LICENSE for details.
{
    'name': 'Téléphonie Wazo — serveur',
    'category': 'Productivity',
    'summary': """Création et encadrement des tenants Wazo""",
    'description': """
Serveur Wazo : création et encadrement des tenants
==================================================
Module de **celui qui exploite le serveur** Wazo, par opposition à
`wazo_phone`, qui est le module d'**un tenant**.

* Création d'un tenant (wazo-auth), avec son **contexte interne** et ses
  **plages d'extensions** (postes, groupes d'appel) ;
* Fabrication de l'**utilisateur administrateur** du tenant et de son
  **jeton d'API** — jamais saisi à la main ;
* Remise des coordonnées au tenant (URL, tenant, jeton, contexte) ;
* Suppression gardée : refusée tant que le tenant porte des postes ou des
  lignes.

Le cloisonnement entre tenants **ne repose pas sur le jeton** : mesuré, un
jeton de tenant peut lire les données d'un autre tenant en changeant l'en-tête
``Wazo-Tenant``. La frontière se place à l'URL (un point d'entrée par tenant),
voir ``doc/P5_WAZO_SERVER_SPEC.md``.
""",
    'version': '1.0',
    'depends': ['wazo_phone'],
    'data': [
        'security/ir.access.csv',
        'views/wazo_server_tenant_views.xml',
        'views/wazo_server_menus.xml',
    ],
    'author': 'Benoît Vézina',
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
