# Part of the voipms_sms Odoo module. See LICENSE for details.
{
    'name': 'VoIP.ms SMS',
    'category': 'Productivity',
    'summary': """Envoyer des SMS via l'API VoIP.ms""",
    'description': """
Boîte d'envoi SMS via VoIP.ms
=============================
* Gestion des DID (numéros d'émetteur) du compte VoIP.ms
* Boîte d'envoi avec segmentation automatique des messages longs
* Synchronisation des DID depuis le serveur
* Configuration de la connexion (utilisateur + token) dans les réglages
""",
    'version': '20.0.1.0.0',
    'depends': ['base'],
    'data': [
        'security/voipms_sms_groups.xml',
        'security/ir.access.csv',
        'views/voipms_did_views.xml',
        'views/voipms_sms_out_views.xml',
        'views/voipms_sms_menus.xml',
        'views/res_config_settings_views.xml',
    ],
    'author': 'Benoît Vézina',
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
