# Part of the asterisk_ari Odoo module. See LICENSE for details.
{
    'name': 'Téléphonie (Asterisk ARI)',
    'category': 'Productivity',
    'summary': """Click-to-call et suivi d'appels via Asterisk ARI (FreePBX)""",
    'description': """
Click-to-call et suivi d'appels
================================
Appel direct depuis la fiche partenaire via l'API ARI de FreePBX/Asterisk,
historique des appels (état, ID ARI, erreurs). Le SMS reste géré par le
module voipms_sms (API REST VoIP.ms) — seul le trafic voix passe par le PBX.
""",
    'version': '20.0.1',
    'license': 'LGPL-3',
    'author': 'Diverse-Cité',
    'website': 'https://www.diverse-cite.com',
    'depends': ['base'],
    'data': [
        'security/asterisk_ari_groups.xml',
        'security/ir.access.csv',
        'views/asterisk_call_views.xml',
        'views/asterisk_ari_menus.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
    },
    'application': True,
    'installable': True,
}
