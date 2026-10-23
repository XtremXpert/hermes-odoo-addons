# Part of the mailcow Odoo module. See LICENSE for details.
"""Adoption des xmlids du tableau de bord renommé ``mailcow_admin`` → ``mailcow``.

Le module ``mailcow_admin`` devient ``mailcow`` : seul le tableau de bord
y reste. Un ``pre-migration`` ne court pas à l'installation d'un module
neuf ; ce ``pre_init_hook`` si. La moitié « exploitation » des xmlids est
adoptée par ``mailcow_tenant`` — ici ne restent que les enregistrements du
tableau de bord. Idempotent.
"""


def adopt_dashboard_xmlids(env):
    # Odoo 20 passe un Environment : le curseur vit sous env.cr.
    env.cr.execute(
        """
        UPDATE ir_model_data
           SET module = 'mailcow'
         WHERE module = 'mailcow_admin'
           AND name LIKE '%%tableau%%'
        """
    )
