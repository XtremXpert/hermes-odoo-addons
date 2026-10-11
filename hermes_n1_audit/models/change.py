"""One authenticated request = one atomic business write and chatter note."""

import hashlib
import json
import math
from datetime import timedelta

from markupsafe import Markup
from psycopg2 import sql

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import AccessError
from odoo.exceptions import UserError

from ..agent_html import agent_html

WRITE_FIELDS = {
    "res.partner": {"name", "city", "street", "street2", "zip", "email", "phone", "mobile"},
    "product.template": {"name", "default_code", "list_price"},
    "crm.lead": {"name", "expected_revenue", "date_deadline"},
    "project.project": {"name"},
    "project.task": {"name", "date_deadline", "priority"},
    "obnl.demande": {"date_demande", "date_entree_prevue", "priorite"},
    "obnl.sejour": {"date_entree", "date_sortie"},
    "contract.contract": {"name", "date_end"},
    "sale.order": {"client_order_ref", "validity_date"},
    "purchase.order": {"partner_ref", "date_order"},
    "account.move": {"ref", "invoice_date", "invoice_date_due"},
    "stock.picking": {"scheduled_date"},
}
SCALAR_TYPES = {
    "char",
    "text",
    "integer",
    "float",
    "monetary",
    "boolean",
    "date",
    "datetime",
    "selection",
}


class HermesN1Change(models.Model):
    _name = "hermes.n1.change"
    _description = "Modification métier documentée par Hermes N1"
    _order = "id desc"

    request_key = fields.Char(required=True, readonly=True, index=True)
    target_model = fields.Char(required=True, readonly=True)
    target_id = fields.Integer(required=True, readonly=True)
    requester_id = fields.Many2one("res.users", required=True, readonly=True)
    agent_id = fields.Many2one("res.users", required=True, readonly=True)
    source_message_id = fields.Many2one(
        "mail.message", required=True, readonly=True, ondelete="restrict"
    )
    chatter_message_id = fields.Many2one(
        "mail.message", required=True, readonly=True, ondelete="restrict"
    )
    reason = fields.Text(required=True, readonly=True)
    before_values = fields.Json(readonly=True)
    after_values = fields.Json(readonly=True)
    _unique_request = models.Constraint("UNIQUE(request_key)", "Demande déjà documentée.")

    def write(self, vals):  # pylint: disable=method-required-super
        raise AccessError(self.env._("L'historique Hermes N1 est immuable."))

    def unlink(self):  # pylint: disable=method-required-super
        raise AccessError(  # pylint: disable=no-raise-unlink
            self.env._("L'historique Hermes N1 est immuable.")
        )

    def _check_agent(self):
        if not self.env.user.has_group("hermes_n1_audit.group_agent"):
            raise AccessError(self.env._("Compte de service Hermes N1 requis."))

    def _editable(self, model):
        if model not in WRITE_FIELDS or model not in self.env:
            return {}
        target = self.env[model]
        if "message_ids" not in target._fields or not callable(
            getattr(target, "message_post", None)
        ):
            return {}
        return {
            name: field
            for name in WRITE_FIELDS[model]
            if (field := target._fields.get(name))
            and field.type in SCALAR_TYPES
            and field.store
            and not field.readonly
            and not field.compute
            and not field.related
        }

    @api.model
    def capabilities(self, model):
        self._check_agent()
        return {
            "model": model,
            "modifiable": sorted(self._editable(model)),
            "audit": "chatter obligatoire, même transaction",
            "creation": False,
            "suppression": False,
        }

    def _requester(self, channel_id, message_id, partner_id):
        # Source IDs are supplied by the trusted gateway context, not by the LLM.
        for value in (channel_id, message_id, partner_id):
            if type(value) is not int or value <= 0:
                raise AccessError(self.env._("Contexte Discuss manquant."))
        message = self.env["mail.message"].browse(message_id).exists()
        if not message:
            raise AccessError(self.env._("Message source absent."))
        message.check_access("read")
        if (
            message.model != "discuss.channel"
            or message.res_id != channel_id
            or message.message_type != "comment"
            or message.author_id.id != partner_id
            or message.date < fields.Datetime.now() - timedelta(hours=1)
        ):
            raise AccessError(self.env._("Message source invalide ou expiré."))
        channel = self.env["discuss.channel"].browse(channel_id)
        channel.check_access("read")
        members = set(channel.sudo().channel_member_ids.partner_id.ids)
        if channel.channel_type != "chat" or members != {self.env.user.partner_id.id, partner_id}:
            raise AccessError(self.env._("Conversation privée avec le demandeur requise."))
        users = (
            self.env["res.users"]
            .sudo()
            .search([("partner_id", "=", partner_id), ("active", "=", True), ("share", "=", False)])
        )
        users = users.filtered(lambda user: user.has_group("base.group_system"))
        if len(users) != 1:
            raise AccessError(self.env._("Demandeur administrateur autorisé requis."))
        return users, message

    @api.model
    def modifier(
        self, model, record_id, values, expected, reason, channel_id, message_id, partner_id
    ):
        self._check_agent()
        actor, source = self._requester(channel_id, message_id, partner_id)
        editable = self._editable(model)
        if (
            type(record_id) is not int
            or record_id <= 0
            or not isinstance(values, dict)
            or not values
            or len(values) > 12
            or not set(values) <= set(editable)
        ):
            raise UserError(
                self.env._("Objet ou champs non modifiables par N1; chatter obligatoire.")
            )
        if not isinstance(expected, dict) or set(expected) != set(values):
            raise UserError(self.env._("Fournir les valeurs actuellement lues pour chaque champ."))
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise UserError(self.env._("Motif obligatoire, de 1 à 1000 caractères."))
        for name, value in values.items():
            field = editable[name]
            if isinstance(value, (dict, list)) or (isinstance(value, str) and len(value) > 2000):
                raise UserError(self.env._("Valeur scalaire trop longue ou invalide."))
            if value is not None and value is not False:
                if field.type in {"integer", "float", "monetary"}:
                    if type(value) not in (int, float) or not math.isfinite(value):
                        raise UserError(self.env._("Valeur numérique finie requise."))
                elif field.type == "boolean":
                    if type(value) is not bool:
                        raise UserError(self.env._("Valeur booléenne requise."))
                elif not isinstance(value, str):
                    raise UserError(self.env._("Valeur texte requise."))
        values = {k: False if v is None else v for k, v in values.items()}
        canonical = json.dumps(
            [self.env.uid, source.id, model, record_id, values],
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        key = hashlib.sha256(canonical.encode()).hexdigest()
        # The entire operation rolls back even if an internal caller catches its error.
        with self.env.cr.savepoint():
            self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", [int(key[:15], 16)])
            previous = self.sudo().search([("request_key", "=", key)], limit=1)
            if previous:
                return previous._result(replayed=True)
            target = self.env[model].with_user(actor).browse(record_id).exists()
            if not target:
                raise UserError(self.env._("Objet absent."))
            target.check_access("read")
            target.check_access("write")
            self.env.cr.execute(
                sql.SQL("SELECT id FROM {} WHERE id = %s FOR UPDATE").format(
                    sql.Identifier(target._table)
                ),
                [record_id],
            )
            target.invalidate_recordset()
            if model in {"sale.order", "purchase.order", "account.move"}:
                allowed = {"draft", "sent"} if model != "account.move" else {"draft"}
                if target.state not in allowed:
                    raise UserError(
                        self.env._("Seuls les documents en brouillon sont modifiables par N1.")
                    )
            if model == "stock.picking" and target.state in {"done", "cancel"}:
                raise UserError(
                    self.env._("Une opération terminée ou annulée ne peut pas être modifiée.")
                )
            before = target.read(sorted(values), load=None)[0]
            before.pop("id", None)
            expected = {k: False if v is None else v for k, v in expected.items()}
            if before != expected:
                raise UserError(
                    self.env._("Conflit : les valeurs ont changé. Relire avant de réessayer.")
                )
            target.with_context(mail_notify_noemail=True, mail_notify_force_send=False).write(
                values
            )
            after = target.read(sorted(values), load=None)[0]
            after.pop("id", None)
            lines = Markup("").join(
                Markup("<li><b>%s</b> (%s) : <code>%s</code> → <code>%s</code></li>")
                % (
                    editable[name].string,
                    name,
                    json.dumps(before[name], ensure_ascii=False),
                    json.dumps(after[name], ensure_ascii=False),
                )
                for name in sorted(values)
            )
            body = Markup(
                "<p><b>Modification Hermes N1</b></p>"
                "<p>Demandée par %s (utilisateur %s), exécutée par %s.</p>"
                '<p class="mb-1"><strong>Motif</strong></p>%s<ul>%s</ul>'
                "<p>Source : Discuss, conversation %s, message %s. Référence : %s.</p>"
            ) % (
                actor.name,
                actor.id,
                self.env.user.name,
                agent_html(reason.strip()),
                lines,
                channel_id,
                source.id,
                key,
            )
            note = target.with_context(
                mail_notify_noemail=True, mail_notify_force_send=False, mail_post_autofollow=False
            ).message_post(
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_note",
                author_id=self.env.user.partner_id.id,
            )
            if not note or note.model != model or note.res_id != record_id:
                raise UserError(self.env._("Documentation du chatter non créée sur l'objet ciblé."))
            audit = self.sudo().create(
                {
                    "request_key": key,
                    "target_model": model,
                    "target_id": record_id,
                    "requester_id": actor.id,
                    "agent_id": self.env.uid,
                    "source_message_id": source.id,
                    "chatter_message_id": note.id,
                    "reason": reason.strip(),
                    "before_values": before,
                    "after_values": after,
                }
            )
            return audit._result()

    def _result(self, replayed=False):
        self.ensure_one()
        return {
            "ok": True,
            "model": self.target_model,
            "id": self.target_id,
            "audit_id": self.id,
            "chatter_message_id": self.chatter_message_id.id,
            "avant": self.before_values,
            "apres": self.after_values,
            "deja_applique": replayed,
        }
