# Part of the wazo_tenant Odoo module. See LICENSE for details.
"""Agrégats du tableau de bord d'exploitation d'un tenant Wazo.

La vue de l'**exploitant du tenant** — par opposition au tableau de bord
personnel de ``wazo_phone`` (mes appels) et à celui de ``wazo_server``
(plateforme, tenants, pont) :

* ``wazo.user`` — santé de la synchronisation des postes ;
* ``wazo.ring.group`` — groupes d'appel et leur effectif ;
* ``wazo.cdr`` — activité des 7 derniers jours, derniers appels, et fraîcheur
  du journal : la date de l'entrée la plus récente dit si la synchro
  planifiée (``data/ir_cron.xml``) tourne encore.

Tout se lit dans l'état local d'Odoo : aucun appel vers Wazo ici. Relire
le PBX reste le geste explicite des boutons de synchronisation des fiches
— le tableau de bord ne fait que constater.
"""

import logging
from datetime import timedelta

from odoo import api
from odoo import fields
from odoo import models

_logger = logging.getLogger(__name__)

#: Fenêtre d'activité du tableau de bord (jours).
FENETRE_JOURS = 7

#: Nombre d'appels récents affichés.
RECENTS = 8


class WazoTenantDashboard(models.AbstractModel):
    _name = "wazo.tenant.dashboard"
    _description = "Tableau de bord d'exploitation du tenant Wazo"

    @api.model
    def get_tenant_dashboard(self):
        """Tous les agrégats du tableau de bord, en un seul appel."""
        User = self.env["wazo.user"]
        Group = self.env["wazo.ring.group"]
        Cdr = self.env["wazo.cdr"]

        users = User.search([], order="name")
        groups = Group.search([], order="name")

        # Usagers : compteurs par état de synchronisation.
        user_states = {state: 0 for state, _ in User._fields["wazo_state"].selection}
        for user in users:
            user_states[user.wazo_state] = user_states.get(user.wazo_state, 0) + 1
        user_items = [
            {
                "id": user.id,
                "name": user.name,
                "extension": user.extension,
                "state": user.wazo_state,
                "error_message": user.error_message or "",
            }
            for user in users
        ]

        # Groupes d'appel : état et effectif — un groupe sans membre
        # n'appelle personne, c'est une alerte silencieuse.
        group_states = {
            state: 0 for state, _ in Group._fields["wazo_state"].selection
        }
        for group in groups:
            group_states[group.wazo_state] = group_states.get(group.wazo_state, 0) + 1
        group_items = [
            {
                "id": group.id,
                "name": group.name,
                "extension": group.extension,
                "member_count": len(group.member_ids),
                "state": group.wazo_state,
            }
            for group in groups
        ]

        # Journal : fenêtre de 7 jours + fraîcheur (dernière entrée vue).
        horizon = fields.Datetime.now() - timedelta(days=FENETRE_JOURS)
        recents = Cdr.search(
            [("date_start", ">=", horizon)], order="date_start desc", limit=RECENTS
        )
        fenetre = Cdr.search_count([("date_start", ">=", horizon)])
        fenetre_manques = Cdr.search_count(
            [("date_start", ">=", horizon), ("answered", "=", False)]
        )
        dernier = Cdr.search([], order="date_start desc", limit=1)
        recent_items = [
            {
                "date_start": cdr.date_start and cdr.date_start.isoformat(),
                "direction": cdr.call_direction,
                "from": cdr.caller_num,
                "to": cdr.destination_num,
                "answered": cdr.answered,
                "duration": cdr.duration,
            }
            for cdr in recents
        ]

        # Nothing configured? Offer the first-setup wizard
        # (wazo_voipms): first trunk, first user, first ring group — guided.
        Trunk = self.env.get("wazo.voipms.trunk")
        no_trunk = Trunk is None or not Trunk.search_count([])
        onboarding = {
            "needed": not users and not groups and no_trunk,
            "action": "wazo_voipms.action_wazo_setup_wizard" if Trunk else False,
        }

        return {
            "onboarding": onboarding,
            "users": {
                "items": user_items,
                "total": len(users),
                "states": user_states,
            },
            "groups": {
                "items": group_items,
                "total": len(groups),
                "states": group_states,
                "empty": sum(1 for item in group_items if not item["member_count"]),
            },
            "calls": {
                "window_days": FENETRE_JOURS,
                "total": fenetre,
                "missed": fenetre_manques,
                "recent": recent_items,
                "last_cdr": dernier
                and dernier.date_start
                and dernier.date_start.isoformat(),
            },
        }
