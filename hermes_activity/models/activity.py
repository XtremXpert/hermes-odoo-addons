"""Operational status only: no prompts, arguments, results or model reasoning."""

import time

from markupsafe import Markup

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import AccessError
from odoo.exceptions import UserError
from odoo.tools import html_sanitize

from .formatting import html_depuis_markdown

TOOLS = {
    "chercher": "Recherche dans Odoo",
    "compter": "Comptage dans Odoo",
    "decrire_modeles": "Consultation des données disponibles",
    "sante_instance": "Vérification de l’instance",
    "modifier": "Modification Odoo en cours",
    "ouvrir_support": "Ouverture du dossier support",
    "lire_support": "Lecture du dossier support",
    "documenter_support": "Documentation du dossier",
    "lire_logs": "Analyse des journaux",
    "etat_git": "Vérification du dépôt",
    "lire_code": "Lecture du code",
    "proposer_code": "Préparation de la proposition de code",
    "etat_staging": "Vérification du staging",
    "deployer_staging": "Déploiement en staging",
    "perimetre_infrastructure": "Consultation du périmètre infrastructure",
    "etat_infrastructure": "Diagnostic de l’infrastructure",
    "proposer_intervention": "Préparation d’une intervention à approuver",
    "lire_intervention": "Vérification de l’intervention",
    "executer_intervention": "Exécution de l’intervention approuvée",
}
STATES = {
    "working": "Analyse de la demande",
    "tool": "Outil en cours",
    "done": "Traitement terminé",
    "error": "Traitement en échec",
    "cancelled": "Traitement interrompu",
}
TERMINAL = {"done", "error", "cancelled"}
AGENT_GROUPS = (
    "hermes_n1_audit.group_agent",
    "hermes_n2_support.group_agent",
    "hermes_n3_infra.group_agent",
)


def _is_agent(env):
    return any(
        env.ref(group, raise_if_not_found=False) and env.user.has_group(group)
        for group in AGENT_GROUPS
    )


class Channel(models.Model):
    _inherit = "discuss.channel"
    hermes_activity_state = fields.Json(readonly=True, copy=False)

    def message_post(self, *, body="", **kwargs):
        # API-key clients send Markdown as a plain RPC string. Convert here
        # as well as in repondre(), without needing a web-session password.
        # Markup from the web route or repondre() is already formatted. With
        # body_is_html, the gateway has already escaped and formatted the text:
        # converting it again would show its tags literally.
        if isinstance(body, str) and not isinstance(body, Markup) and _is_agent(self.env):
            texte = body if kwargs.get("body_is_html") else html_depuis_markdown(body)
            body = Markup(html_sanitize(texte))
        return super().message_post(body=body, **kwargs)

    def write(self, vals):
        if "hermes_activity_state" in vals and not self.env.su:
            raise AccessError(self.env._("Utiliser la façade d’activité Hermes."))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any("hermes_activity_state" in vals for vals in vals_list):
            raise AccessError(self.env._("Utiliser la façade d’activité Hermes."))
        return super().create(vals_list)


class Activity(models.AbstractModel):
    _name = "hermes.activity"
    _description = "État visuel de traitement Hermes"

    def _source(self, channel_id, message_id, partner_id):
        if not _is_agent(self.env):
            raise AccessError(self.env._("Identité agent requise."))
        return self.env["hermes.n1.change"]._requester(channel_id, message_id, partner_id)

    @api.model
    def repondre(self, channel_id, message_id, partner_id, text):
        self._source(channel_id, message_id, partner_id)
        if not isinstance(text, str) or not 1 <= len(text) <= 100000:
            raise UserError(self.env._("Réponse invalide."))
        channel = self.env["discuss.channel"].browse(channel_id)
        body = Markup(html_sanitize(html_depuis_markdown(text)))
        message = channel.message_post(
            body=body, message_type="comment", subtype_xmlid="mail.mt_comment"
        )
        return message.id

    @api.model
    def publier(self, channel_id, message_id, partner_id, sequence, state, tool=None):
        self._source(channel_id, message_id, partner_id)
        if type(sequence) is not int or sequence < 0 or state not in STATES:
            raise UserError(self.env._("État invalide."))
        if tool is not None and tool not in TOOLS:
            raise UserError(self.env._("Outil inconnu."))
        channel = self.env["discuss.channel"].sudo().browse(channel_id)
        self.env.cr.execute("SELECT id FROM discuss_channel WHERE id = %s FOR UPDATE", [channel_id])
        channel.invalidate_recordset(["hermes_activity_state"])
        old = channel.hermes_activity_state or {}
        if old.get("message_id", 0) > message_id:
            return {"accepted": False}
        same = old.get("message_id") == message_id
        if same and (old.get("sequence", -1) >= sequence or old.get("state") in TERMINAL):
            return {"accepted": False}
        now = time.time()
        label = TOOLS[tool] if state == "tool" and tool else STATES[state]
        steps = [dict(step) for step in old.get("steps", [])] if same else []
        step_count = old.get("step_count", len(steps)) if same else 0
        # Refreshes keep the current step alive without adding duplicate rows.
        if not steps or (steps[-1]["state"], steps[-1].get("tool")) != (state, tool):
            if steps:
                steps[-1]["ended_at"] = now
            step_count += 1
            steps.append(
                {
                    "number": step_count,
                    "state": state,
                    "tool": tool,
                    "label": label,
                    "started_at": now,
                    "ended_at": now if state in TERMINAL else None,
                }
            )
        steps = steps[-50:]
        value = {
            "message_id": message_id,
            "sequence": sequence,
            "state": state,
            "label": label,
            "steps": steps,
            "step_count": step_count,
            "agent": self.env.user.name,
            "started_at": old["started_at"] if same else now,
            "updated_at": now,
        }
        channel.write({"hermes_activity_state": value})
        self._heartbeat()
        return {"accepted": True}

    @api.model
    def lire(self, channel_id):
        if type(channel_id) is not int or channel_id < 1:
            raise AccessError(self.env._("Conversation invalide."))
        channel = self.env["discuss.channel"].browse(channel_id).exists()
        if not channel:
            raise AccessError(self.env._("Conversation absente."))
        channel.check_access("read")
        if self.env.user.partner_id not in channel.sudo().channel_member_ids.partner_id:
            raise AccessError(self.env._("Conversation privée requise."))
        return channel.sudo().hermes_activity_state or False
