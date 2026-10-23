# Part of the wazo_tenant Odoo module. See LICENSE for details.
"""Adoption des xmlids déplacés de ``wazo_phone`` vers ``wazo_tenant``.

Le découpage sort la couche exploitation (``wazo.user``, ``wazo.ring.group``,
``wazo.cdr``, inventaire, réglages de connexion, groupes) de ``wazo_phone``.
Sans renommée, la mise à jour de ``wazo_phone`` supprimerait vues, menus,
actions et règles d'accès devenus orphelins, puis l'installation de
``wazo_tenant`` les recréerait — en double, et les utilisateurs perdraient
leurs groupes.

Un ``pre-migration`` ne s'exécute pas à l'installation d'un module neuf :
ce ``pre_init_hook`` court toujours, lui. Idempotent.
"""

#: Préfixes des xmlids déplacés. Le tableau de bord, le softphone et le
#: pont voip restent dans ``wazo_phone`` : exclus par le NOT LIKE final.
MOVED_PREFIXES = (
    "wazo_user%",
    "wazo_ring_group%",
    "wazo_cdr%",
    "wazo_extension%",
    "wazo_res_config_settings_view",
    "access_wazo_%",
    "model_wazo_%",
    "field_wazo_%",
    "field_res_partner__wazo_%",
    "menu_wazo_%",
    "action_wazo_%",
    "group_wazo_%",
    "ir_cron_wazo_cdr%",
)


def adopt_wazo_phone_xmlids(env):
    # Odoo 20 passe un Environment : le curseur vit sous env.cr.
    env.cr.execute(
        """
        UPDATE ir_model_data
           SET module = 'wazo_tenant'
         WHERE module = 'wazo_phone'
           AND name LIKE ANY (%(prefixes)s)
           AND name NOT LIKE '%%dashboard%%'
           AND name NOT LIKE '%%softphone%%'
           AND name NOT LIKE '%%voip%%'
        """,
        {"prefixes": list(MOVED_PREFIXES)},
    )
