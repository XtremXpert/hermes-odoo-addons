# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Bouclage d'appel et tableau de bord téléphonie.

Deux responsabilités, exposées par le navigateur (softphone et page de
tableau de bord) :

* ``res.users`` — cycle de vie d'un appel signalé par l'onglet qui détient
  la session SIP : ``notify_wazo_incoming_call`` diffuse l'appel entrant sur
  le canal bus de l'utilisateur (P3.3g — toutes ses sessions sont déjà
  abonnées à ``res.users``, voir ``ir_websocket._build_bus_channel_list``),
  et ``finalize_wazo_call`` consigne la fin : note sur le contact
  identifié, activité « Appel » pour un entrant manqué, notification bus
  « appel manqué » vers les autres appareils.

* ``wazo.cdr`` — ``get_wazo_dashboard`` aggrège le journal d'appels pour le
  tableau de bord OWL : indicateurs du périmètre « mes appels » (poste de
  l'utilisateur courant) et, pour le groupe gestionnaire, le périmètre
  « équipe » avec la répartition par poste.

Aucun appel Wazo n'est passé ici : tout se fait sur les données locales.
"""

import re
from datetime import timedelta

from odoo import api
from odoo import fields
from odoo import models

DIRECTIONS = ("inbound", "outbound", "internal")
DASHBOARD_MAX_DAYS = 365
DASHBOARD_RECENT_LIMIT = 8
DASHBOARD_AGENT_LIMIT = 10


def _digits(number):
    """Les chiffres d'un numéro, sans le formatage."""
    return re.sub(r"\D", "", str(number or ""))


def _format_seconds(seconds):
    """« 2 min 34 s » — la forme lisible d'une durée en secondes."""
    seconds = max(int(seconds or 0), 0)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return "%d h %02d min" % (hours, minutes)
    if minutes:
        return "%d min %02d s" % (minutes, sec)
    return "%d s" % sec


class ResUsersWazoCall(models.Model):
    """Signalements d'appel émis par l'onglet propriétaire de la session."""

    _inherit = "res.users"

    def notify_wazo_incoming_call(self, info=None):
        """Diffuse un appel entrant sur le canal bus de l'utilisateur (P3.3g).

        L'onglet qui détient la couche SIP reçoit l'INVITE et appelle cette
        méthode : chaque session de l'utilisateur — autres navigateurs,
        autres appareils — est abonnée à son canal ``res.users`` et reçoit
        donc la notification sans enregistrer de canal supplémentaire.

        Le navigateur qui a émis ignore sa propre notification (il sonne
        déjà par la couche SIP / le canal inter-onglets).
        """
        self.ensure_one()
        info = info or {}
        self.env.user._bus_send(
            "wazo_phone.incoming_call",
            {
                "num": str(info.get("num") or info.get("from") or ""),
                "name": str(info.get("name") or ""),
            },
        )
        return True

    def finalize_wazo_call(self, info=None):
        """Consigne la fin d'un appel.

        Appelé par l'onglet propriétaire à l'événement « fin de session ».
        ``info`` porte ``num`` (l'autre partie), ``direction``, ``answered``
        et ``duration`` (secondes).

        * contact identifié (même logique que le rapprochement CDR) → note
          sur sa fiche ;
        * entrant **manqué** → activité « Appel » pour l'utilisateur sur le
          contact, et notification bus « appel manqué » vers toutes ses
          sessions (un appareil sans endpoint enregistré est ainsi prévenu).

        Retourne un résumé consommé par le navigateur (``partner_id``,
        ``partner_name``, ``missed``, ``activity_id``).
        """
        self.ensure_one()
        info = info or {}
        direction = info.get("direction")
        if direction not in DIRECTIONS:
            direction = "outbound"
        num = str(info.get("num") or "")
        answered = bool(info.get("answered"))
        duration = int(info.get("duration") or 0)
        cdr = self.env["wazo.cdr"]
        # Le matching attend (appelant, destination) : l'autre partie est
        # l'appelant pour un entrant, la destination sinon.
        if direction == "inbound":
            partner = cdr._find_partner_for_cdr(num, "", {})
        else:
            partner = cdr._find_partner_for_cdr("", num, {})
        missed = direction == "inbound" and not answered
        if partner:
            partner.message_post(
                body=self._wazo_call_note(direction, num, answered, duration),
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
        result = {
            "missed": missed,
            "partner_id": partner.id if partner else False,
            "partner_name": partner.display_name if partner else False,
            "activity_id": False,
        }
        if not missed:
            return result
        if partner:
            activity = self.env["mail.activity"].create(
                {
                    "res_model_id": self.env["ir.model"]._get("res.partner").id,
                    "res_id": partner.id,
                    "activity_type_id": self.env.ref(
                        "mail.mail_activity_data_call"
                    ).id,
                    "summary": self.env._("Appel manqué de %s") % num,
                    "user_id": self.id,
                    "date_deadline": fields.Date.today(),
                }
            )
            result["activity_id"] = activity.id
        self.env.user._bus_send(
            "wazo_phone.missed_call",
            {
                "num": num,
                "name": str(info.get("name") or ""),
                "partner_id": result["partner_id"],
                "partner_name": result["partner_name"],
            },
        )
        return result

    def _wazo_call_note(self, direction, num, answered, duration):
        """Le corps de la note consignée sur le contact."""
        if direction == "inbound":
            verb = (
                self.env._("Appel entrant de %(num)s — répondu")
                if answered
                else self.env._("Appel entrant de %(num)s — manqué")
            )
        elif direction == "internal":
            verb = self.env._("Appel interne vers %(num)s")
        else:
            verb = self.env._("Appel sortant vers %(num)s")
        note = verb % {"num": num or self.env._("inconnu")}
        if duration:
            note += " (%s)" % _format_seconds(duration)
        return note


class WazoCdrDashboard(models.Model):
    """Agrégats du journal d'appels pour le tableau de bord téléphonie."""

    _inherit = "wazo.cdr"

    @api.model
    def get_wazo_dashboard(self, days=30):
        """Indicateurs du tableau de bord, périmètres « mes appels » et « équipe ».

        ``mine`` filtre le journal sur le poste Wazo de l'utilisateur courant
        (appelant ou destination) ; ``team`` n'est calculé que pour le groupe
        gestionnaire et ajoute la répartition par poste. Les séries sont
        comptées **par jour civil UTC** (``date_trunc``).
        """
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 30
        days = min(max(days, 1), DASHBOARD_MAX_DAYS)
        since = fields.Datetime.now() - timedelta(days=days)
        user = self.env.user
        # res.users hérite des champs du contact par délégation (_inherits) :
        # ``wazo_user_id`` vit sur res.partner.
        extension = user.wazo_user_id.extension or ""
        payload = {
            "days": days,
            "extension": extension,
            # Sans poste, « mes appels » est vide plutôt que tout le journal.
            "mine": (
                self._dashboard_scope(since, extension)
                if extension
                else self._dashboard_empty()
            ),
        }
        if user.has_group("wazo_tenant.group_wazo_manager"):
            payload["team"] = self._dashboard_scope(since, "")
            payload["team"]["agents"] = self._dashboard_agents(since)
        else:
            payload["team"] = False
        return payload

    def _dashboard_empty(self):
        """Un périmètre sans appel (utilisateur sans poste Wazo)."""
        return {
            "total": 0,
            "answered": 0,
            "missed": 0,
            "inbound": 0,
            "outbound": 0,
            "internal": 0,
            "duration_sum": 0,
            "duration_avg": 0,
            "series": [],
            "recent": [],
        }

    def _scope_clause(self, extension):
        """Clause WHERE du périmètre (et ses paramètres)."""
        if extension:
            return " AND (caller_num = %s OR destination_num = %s)", [extension, extension]
        return "", []

    def _dashboard_scope(self, since, extension):
        """Compteurs, série quotidienne et derniers appels d'un périmètre."""
        clause, params = self._scope_clause(extension)
        self.env.cr.execute(
            "SELECT count(*),"
            " count(*) FILTER (WHERE answered),"
            " count(*) FILTER (WHERE call_direction = 'inbound' AND NOT answered),"
            " count(*) FILTER (WHERE call_direction = 'inbound'),"
            " count(*) FILTER (WHERE call_direction = 'outbound'),"
            " count(*) FILTER (WHERE call_direction = 'internal'),"
            " COALESCE(sum(duration), 0)"
            " FROM wazo_cdr WHERE date_start >= %s" + clause,
            [since, *params],
        )
        (
            total,
            answered,
            missed,
            inbound,
            outbound,
            internal,
            duration_sum,
        ) = self.env.cr.fetchone()
        domain = [("date_start", ">=", since)]
        if extension:
            domain += ["|", ("caller_num", "=", extension), ("destination_num", "=", extension)]
        recent = self.search(domain, limit=DASHBOARD_RECENT_LIMIT)
        return {
            "total": total,
            "answered": answered,
            "missed": missed,
            "inbound": inbound,
            "outbound": outbound,
            "internal": internal,
            "duration_sum": duration_sum,
            "duration_avg": int(duration_sum / total) if total else 0,
            "series": self._dashboard_series(since, clause, params),
            "recent": [self._dashboard_entry(c) for c in recent],
        }

    def _dashboard_series(self, since, clause, params):
        """Appels par jour civil UTC, répondus et manqués distingués."""
        self.env.cr.execute(
            "SELECT date_trunc('day', date_start)::date AS jour,"
            " count(*),"
            " count(*) FILTER (WHERE answered),"
            " count(*) FILTER (WHERE call_direction = 'inbound' AND NOT answered)"
            " FROM wazo_cdr WHERE date_start >= %s" + clause + " GROUP BY 1 ORDER BY 1",
            [since, *params],
        )
        return [
            {"day": str(jour), "total": total, "answered": answered, "missed": missed}
            for jour, total, answered, missed in self.env.cr.fetchall()
        ]

    def _dashboard_agents(self, since):
        """Répartition par poste (périmètre équipe, toutes directions)."""
        self.env.cr.execute(
            "SELECT agent, count(*), COALESCE(sum(duree), 0),"
            " count(*) FILTER (WHERE manque) FROM ("
            "   SELECT CASE WHEN call_direction = 'outbound' THEN caller_num"
            "          ELSE destination_num END AS agent,"
            "      duration AS duree,"
            "      (call_direction = 'inbound' AND NOT answered) AS manque"
            "   FROM wazo_cdr WHERE date_start >= %s"
            " ) appels GROUP BY agent ORDER BY count(*) DESC LIMIT %s",
            [since, DASHBOARD_AGENT_LIMIT],
        )
        rows = self.env.cr.fetchall()
        if not rows:
            return []
        # Poste → utilisateur Wazo (et contact) pour un affichage nommé.
        users = self.env["wazo.user"].search(
            [("extension", "in", [row[0] for row in rows])]
        )
        by_ext = {u.extension: u for u in users}
        agents = []
        for agent, total, duration, missed in rows:
            wiz = by_ext.get(agent)
            agents.append(
                {
                    "extension": agent,
                    "name": wiz.name if wiz else agent,
                    "partner_id": wiz.partner_id.id if wiz and wiz.partner_id else False,
                    "total": total,
                    "duration": duration,
                    "missed": missed,
                }
            )
        return agents

    def _dashboard_entry(self, cdr):
        """Une ligne « dernier appel » du tableau de bord."""
        if cdr.call_direction == "inbound":
            num, name = cdr.caller_num, cdr.caller_name
        else:
            num, name = cdr.destination_num, cdr.destination_name
        return {
            "id": cdr.id,
            "date": cdr.date_start.isoformat() if cdr.date_start else False,
            "direction": cdr.call_direction,
            "answered": cdr.answered,
            "duration": cdr.duration,
            "num": num,
            "name": name,
            "partner_id": cdr.partner_id.id if cdr.partner_id else False,
            "partner_name": cdr.partner_id.display_name if cdr.partner_id else False,
        }
