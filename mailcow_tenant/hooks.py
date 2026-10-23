# Part of the mailcow_tenant Odoo module. See LICENSE for details.
"""Adoption des xmlids déplacés de ``mailcow_admin`` vers ``mailcow_tenant``.

Le découplace sort la couche exploitation (domaines, boîtes, alias, client
API, réglages de connexion) de ``mailcow_admin``. Sans renommée, la mise à
jour de l'ancien module supprimerait vues, menus, actions et règles
d'accès devenus orphelins, puis l'installation de ``mailcow_tenant`` les
recréerait — en double, et les utilisateurs perdraient leurs groupes.

Un ``pre-migration`` ne s'exécute pas à l'installation d'un module neuf :
c'est pourquoi l'adoption passe par ce ``pre_init_hook``, qui lui court
toujours. Idempotent : simple UPDATE, ne fait rien si les lignes
n'existent pas.
"""


def adopt_mailcow_admin_xmlids(env):
    # Odoo 20 passe un Environment : le curseur vit sous env.cr.
    # Tout ce qui n'est pas le tableau de bord (il reste dans ``mailcow``).
    env.cr.execute(
        """
        UPDATE ir_model_data
           SET module = 'mailcow_tenant'
         WHERE module = 'mailcow_admin'
           AND name NOT LIKE '%%tableau%%'
        """
    )
