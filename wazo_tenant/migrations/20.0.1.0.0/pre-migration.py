# Part of the wazo_tenant Odoo module. See LICENSE for details.
"""Adopte les xmlids déplacés de ``wazo_phone`` vers ``wazo_tenant``.

Le découpage sort les modèles tenant (``wazo.user``, ``wazo.ring.group``,
``wazo.cdr``, inventaire, réglages de connexion) de ``wazo_phone``. Sans
cette renommée, la mise à jour de ``wazo_phone`` supprimerait les vues,
menus, actions et règles d'accès désormais « orphelins » chez lui, puis
l'installation de ``wazo_tenant`` les recréerait — avec perte des
personnalisations. En adoptant les xmlids ici, les enregistrements
passent de module sans être détruits ni dupliqués.

Idempotent : simple UPDATE, ne fait rien si les lignes sont absentes.
"""

#: Préfixes des xmlids déplacés vers wazo_tenant. Tout ce qui commence
#: par ``wazo_`` mais reste dans wazo_phone (tableau de bord, softphone)
#: est exclu par le NOT LIKE du script. Les réglages softphone gardent
#: leur xmlid wazo_phone (champs définis par voip_bridge, qui reste).
MOVED_PREFIXES = (
    "wazo_user%",            # modèle, vues, action des utilisateurs
    "wazo_ring_group%",      # groupes d'appel + membres
    "wazo_cdr%",             # journal d'appels
    "wazo_extension%",       # mixin, inventaire des postes
    "wazo_res_config_settings_view",  # vue de connexion (sans _phone)
    "access_wazo_%",         # règles ir.model.access déplacées
    "model_wazo_%",          # ir.model des modèles déplacés
    "field_wazo_%",          # champs de ces modèles
    "field_res_partner__wazo_%",      # wazo_user_id sur le contact
    "menu_wazo_%",           # menus — dashboard exclu ci-dessous
    "action_wazo_%",         # actions — dashboard exclu ci-dessous
    "group_wazo_%",          # groupes de sécurité
    "ir_cron_wazo_cdr%",     # tâche planifiée de synchro CDR
    "view_partner_form%wazo%",        # héritage fiche contact
)


def migrate(cr, version):
    cr.execute(
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
