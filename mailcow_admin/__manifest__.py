# Part of the mailcow_admin Odoo module. See LICENSE for details.
{
    'name': 'Mailcow Admin',
    'category': 'Productivity',
    'summary': """Administer un serveur Mailcow depuis Odoo""",
    'description': """
Administer un serveur Mailcow v1 depuis Odoo
=============================================
* Gestion des domaines, boîtes mail et alias du serveur Mailcow
* Création, mise à jour et suppression sur le serveur via des boutons
* Synchronisation (import) depuis le serveur Mailcow
* Réinitialisation des mots de passe (jamais stockés dans Odoo)
* Configuration de la connexion (URL + clé API) dans les réglages
""",
    'version': '19.5.1.0.0',
    'depends': ['base', 'mail'],
    'data': [
        'security/mailcow_admin_groups.xml',
        'security/ir.access.csv',
        'views/mailcow_email_address_views.xml',
        'views/mailcow_domain_views.xml',
        'views/mailcow_mailbox_views.xml',
        'views/mailcow_mailbox_password_wizard_views.xml',
        'views/mailcow_alias_views.xml',
        'views/res_config_settings_views.xml',
        'views/mailcow_admin_menus.xml',
        'views/mailcow_sync_views.xml',
    ],
    'author': 'Benoît Vézina',
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}