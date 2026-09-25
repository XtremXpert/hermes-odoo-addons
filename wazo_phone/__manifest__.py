# Part of the wazo_phone Odoo module. See LICENSE for details.
{
    'name': 'Téléphonie Wazo',
    'category': 'Productivity',
    'summary': """Connecteur Wazo Platform : utilisateurs, extensions et journal d'appels""",
    'description': """
Connecteur Wazo Platform
========================
* Connexion au serveur Wazo (URL, token API, tenant) via les réglages
* Création d'utilisateurs Wazo (ligne SIP, poste, endpoint, messagerie vocale)
  depuis un contact Odoo
* Création de groupes d'appel (ring groups) : poste pris dans la plage des
  groupes du contexte, membres rattachés par utilisateur Wazo
* Inventaire des postes du contexte : rattachements, postes orphelins,
  correspondance avec les fiches Odoo
* Journal d'appels synchronisé depuis wazo-call-logd (cron + bouton manuel)
* Statistiques d'appels par contact
""",
    'version': '19.5.3',
    'depends': ['base', 'web'],
    'data': [
        'security/wazo_groups.xml',
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/res_partner_views.xml',
        'views/wazo_user_views.xml',
        'views/wazo_ring_group_views.xml',
        'views/wazo_context_inventory_views.xml',
        'views/wazo_cdr_views.xml',
        'views/res_config_settings_views.xml',
        'views/wazo_menus.xml',
    ],
    'author': 'Benoît Vézina',
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
    'assets': {
        'web.assets_backend': [
            # Sans ordre explicite, Odoo trie les modules du paquet et place
            # wazo_phone avant « web » (« waz » < « web ») : nos fichiers
            # passeraient devant module_loader.js, qui définit odoo.define, et
            # le client web mourrait au chargement sans la moindre erreur côté
            # serveur. La directive « après le chargeur » ne dépend ni des noms
            # ni du tri.
            ('after', 'web/static/src/module_loader.js',
             'wazo_phone/static/src/softphone/*.js'),
            'wazo_phone/static/src/softphone/wazo_softphone_templates.xml',
        ],
        'wazo_phone.assets_sip': [
            'wazo_phone/static/lib/sip.js',
        ],
        # Bundle du SDK officiel Wazo (P3.3f), chargé à la demande
        # (``loadBundle``) : il ne pénalise pas le webclient tant que le
        # moteur SDK n'est pas sélectionné. Vendorisé enveloppé → ses
        # exports vivent sous ``window.WazoSDK``, pas sur la racine.
        'wazo_phone.assets_sdk': [
            'wazo_phone/static/lib/wazo-sdk.js',
        ],
    },
}
