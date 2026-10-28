"""Business access through the authenticated requester's ORM permissions."""

import hashlib
import json
import math
import re
from datetime import datetime

from markupsafe import Markup
from psycopg2 import sql

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import AccessError
from odoo.exceptions import UserError
from odoo.tools.json import json_default

from ..agent_html import agent_html
from ..agent_html import values_table

# Models N1 never reaches, even for reads: internals, credentials, and the
# agent's own administration objects (those stay N3-only by contract).
FORBIDDEN = (
    "ir.",
    "base.",
    "auth.",
    "bus.",
    "web.",
    "hermes.",
    "k8s.",
    "automation.",
    "queue.",
    "res.groups",
    "res.config",
    "res.bank",
    "res.partner.bank",
    "payment.",
    "fetchmail.",
    "iap.",
    "sms.",
)
# Readable when the employee may read them, but never writable through N1:
# assistance means following the requester's rights, not editing Discuss,
# users or company settings on their behalf.
TECHNICAL = (
    "mail.",
    "discuss.",
    "res.users",
    "res.company",
)
SENSITIVE = re.compile(
    r"password|passwd|secret|token|credential|private_key|api_key|python|code_compute|signup|oauth|totp|session",
    re.I,
)
SCALARS = {
    "char",
    "text",
    "html",
    "many2many",
    "one2many",
    "integer",
    "float",
    "monetary",
    "boolean",
    "date",
    "datetime",
    "selection",
    "many2one",
    "binary",
    "reference",
    "properties",
    "json",
}
CONTROL = {
    "id",
    "state",
    "company_id",
    "company_ids",
    "create_uid",
    "create_date",
    "write_uid",
    "write_date",
}
# Assignment may reference an existing internal user; it never edits that user.
REFERENCE_ONLY = {"res.users"}
ACTION_LABELS = {"archive": "archivage", "unarchive": "désarchivage", "unlink": "suppression"}


def json_value(value):
    # Preserve microseconds: a second write in the same second must conflict too.
    return json.loads(
        json.dumps(
            value,
            default=lambda obj: (
                obj.isoformat(sep=" ") if isinstance(obj, datetime) else json_default(obj)
            ),
            allow_nan=False,
        )
    )


class Business(models.Model):
    _inherit = ["hermes.n1.change", "mail.thread"]
    _name = "hermes.n1.change"

    chatter_message_id = fields.Many2one(
        "mail.message", required=False, readonly=True, ondelete="restrict"
    )

    def _business(self, model, actor, writable=False):
        if (
            not isinstance(model, str)
            or model.startswith(FORBIDDEN)
            or (writable and model.startswith(TECHNICAL))
            or model not in self.env
        ):
            raise AccessError(self.env._("Objet technique ou absent ; administration N3 requise."))
        target = self.env[model].with_user(actor)
        if target._transient or target._abstract or not target._auto:
            raise AccessError(self.env._("Objet non métier."))
        target.check_access("read")
        return target

    def _business_fields(self, target, writable=False):
        # fields_get applies field-level group restrictions for the human actor.
        visible = target.fields_get(
            attributes=["string", "type", "selection", "relation", "required", "readonly"]
        )
        result = {}
        for name, desc in visible.items():
            field = target._fields[name]
            if field.type not in SCALARS or SENSITIVE.search(name):
                continue
            # Relations: never expose FORBIDDEN comodels; for writable
            # exposure TECHNICAL comodels are hidden too, except the
            # res.users reference used for assignment.
            if field.type in ("many2one", "many2many", "one2many"):
                user_reference = (
                    field.comodel_name in REFERENCE_ONLY
                    and field.type in ("many2one", "many2many")
                    and name in ("user_id", "user_ids")
                )
                if field.comodel_name.startswith(FORBIDDEN) or (
                    writable
                    and field.comodel_name.startswith(TECHNICAL)
                    and not user_reference
                ):
                    continue
            if writable:
                # Odoo stores website page markup on the delegated ir.ui.view.
                # Expose only the page-facing inverse field, never generic
                # ir.ui.view records or their arch_db implementation field.
                page_markup = (
                    target._name == "website.page"
                    and name == "arch"
                    and field.related == "view_id.arch"
                    and field.inverse
                )
                if (
                    name in CONTROL
                    or field.readonly
                    or ((not field.store or field.related) and not page_markup)
                ):
                    continue
            result[name] = desc
        return result

    def _business_actor(self, channel_id, message_id, partner_id):
        self._check_agent()
        return self._requester(channel_id, message_id, partner_id)

    @api.model
    def explorer(self, channel_id, message_id, partner_id, model=None, offset=0):
        actor, _ = self._business_actor(channel_id, message_id, partner_id)
        if model:
            target = self._business(model, actor)
            readonly = model.startswith(TECHNICAL)
            return {
                "model": model,
                "fields": self._business_fields(target),
                "editable": {} if readonly else self._business_fields(target, writable=True),
                "operations": ["read"] if readonly else ["read", "create", "write", "unlink"],
                "actions": (
                    []
                    if readonly or "active" not in target._fields
                    else ["archive", "unarchive"]
                ),
                "note": (
                    "Droits ORM du demandeur. "
                    "Relations : liaison à des objets existants uniquement."
                ),
            }
        if type(offset) is not int or offset < 0:
            raise UserError(self.env._("Pagination invalide."))
        available = []
        for name in sorted(self.env.registry.models):
            try:
                self._business(name, actor)
                available.append(name)
            except AccessError:
                continue
        return {
            "models": available[offset : offset + 80],
            "total": len(available),
            "next_offset": offset + 80 if offset + 80 < len(available) else None,
        }

    @api.model
    def lire_metier(
        self,
        model,
        channel_id,
        message_id,
        partner_id,
        domain=None,
        names=None,
        limit=20,
        offset=0,
        include_archived=False,
    ):
        actor, _ = self._business_actor(channel_id, message_id, partner_id)
        target = self._business(model, actor)
        if type(include_archived) is not bool:
            raise UserError(self.env._("include_archived doit être booléen."))
        if include_archived:
            target = target.with_context(active_test=False)
        available = self._business_fields(target)
        names = names or [n for n in ("id", "name") if n in available]
        if (
            not isinstance(names, list)
            or not names
            or len(names) > 40
            or any(not isinstance(n, str) or n not in available for n in names)
        ):
            raise UserError(self.env._("Champs non autorisés."))
        if type(limit) is not int or not 1 <= limit <= 80 or type(offset) is not int or offset < 0:
            raise UserError(self.env._("Pagination invalide."))
        domain = [] if domain is None else domain
        if not isinstance(domain, list) or len(domain) > 40:
            raise UserError(self.env._("Domaine invalide."))
        for term in domain:
            if isinstance(term, str) and term in ("&", "|", "!"):
                continue
            if not isinstance(term, (list, tuple)) or len(term) != 3:
                raise UserError(self.env._("Filtre invalide."))
            name, operator, value = term
            if (
                not isinstance(name, str)
                or name not in available
                or operator
                not in ("=", "!=", ">", "<", ">=", "<=", "in", "not in", "ilike", "like")
            ):
                raise UserError(self.env._("Filtre non autorisé."))
            if isinstance(value, dict) or (
                isinstance(value, list)
                and (len(value) > 80 or any(isinstance(v, (dict, list)) for v in value))
            ):
                raise UserError(self.env._("Valeur de filtre invalide."))
        return {
            "model": model,
            "rows": json_value(
                target.search(domain, limit=limit, offset=offset, order="id").read(names, load=None)
            ),
            "count": target.search_count(domain),
            "limit": limit,
            "offset": offset,
        }

    def _business_values(self, target, actor, values):
        for name, value in values.items():
            field = target._fields[name]
            if field.type in ("many2one", "many2many", "one2many"):
                if field.type == "many2one":
                    ids = [] if value is None or value is False else [value]
                else:
                    if not isinstance(value, list) or len(value) > 80:
                        raise UserError(
                            self.env._("Commandes relationnelles requises, au plus 80.")
                        )
                    ids = []
                    for command in value:
                        # No nested create/write/delete: each object gets its own audit.
                        if not isinstance(command, (list, tuple)) or len(command) != 3:
                            raise UserError(self.env._("Commande relationnelle invalide."))
                        op, record_id, payload = command
                        if type(op) is not int:
                            raise UserError(self.env._("Commande relationnelle invalide."))
                        if op in (3, 4) and payload == 0:
                            ids.append(record_id)
                        elif (
                            op == 6
                            and record_id == 0
                            and isinstance(payload, list)
                            and len(payload) <= 80
                        ):
                            ids.extend(payload)
                        elif op == 5 and record_id == 0 and payload == 0:
                            pass
                        else:
                            raise UserError(
                                self.env._(
                                    "Créer ou modifier les objets liés séparément, "
                                    "avec leur propre journal."
                                )
                            )
                        if field.type == "one2many" and op != 4:
                            # Removing a child can cascade-delete it through its inverse field.
                            raise UserError(self.env._("Modifier les objets enfants séparément."))
                if any(type(i) is not int or i <= 0 for i in ids):
                    raise UserError(self.env._("Identifiants relationnels positifs requis."))
                if field.comodel_name in REFERENCE_ONLY:
                    related = self.env[field.comodel_name].with_user(actor).browse(ids)
                    related.check_access("read")
                    if any(not r.active or r.share for r in related.exists()):
                        raise AccessError(
                            self.env._("Affectation à un utilisateur interne actif requise.")
                        )
                else:
                    related = self._business(field.comodel_name, actor).browse(ids)
                    related.check_access("read")
                if len(related.exists()) != len(set(ids)):
                    raise UserError(self.env._("Objet lié absent."))
            elif value is None or value is False:
                continue
            elif field.type in ("integer", "float", "monetary"):
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise UserError(self.env._("Nombre fini requis."))
            elif field.type == "boolean":
                if type(value) is not bool:
                    raise UserError(self.env._("Booléen requis."))
            elif not isinstance(value, str) or len(value) > 32000:
                raise UserError(self.env._("Valeur texte invalide."))

    @api.model
    def corriger_metier(
        self,
        model,
        values,
        reason,
        channel_id,
        message_id,
        partner_id,
        record_id=None,
        expected=None,
    ):
        actor, source = self._business_actor(channel_id, message_id, partner_id)
        target_model = self._business(model, actor, writable=True)
        editable = self._business_fields(target_model, writable=True)
        if (
            not isinstance(values, dict)
            or not values
            or len(values) > 40
            or not set(values) <= set(editable)
        ):
            raise UserError(self.env._("Champs non modifiables ; consulter explorer."))
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise UserError(self.env._("Motif obligatoire."))
        creating = record_id is None
        if not creating and (
            type(record_id) is not int
            or record_id <= 0
            or not isinstance(expected, dict)
            or set(expected) != set(values)
        ):
            raise UserError(self.env._("Identifiant et valeurs précédentes requis."))
        if creating and expected not in (None, {}):
            raise UserError(self.env._("Pas de valeurs précédentes pour une création."))
        self._business_values(target_model, actor, values)
        expected = json_value(expected)
        values = {k: False if v is None else v for k, v in values.items()}
        key = hashlib.sha256(
            json.dumps(
                [self.env.uid, source.id, model, record_id, values, expected],
                sort_keys=True,
                allow_nan=False,
            ).encode()
        ).hexdigest()
        with self.env.cr.savepoint():
            self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", [int(key[:15], 16)])
            previous = self.sudo().search([("request_key", "=", key)], limit=1)
            if previous:
                return previous._result(replayed=True)
            if creating:
                target_model.check_access("create")
                target = target_model.with_context(
                    mail_create_nosubscribe=True, mail_notify_noemail=True
                ).create(values)
                before = {}
            else:
                target = target_model.browse(record_id).exists()
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
                # Validated financial/logistics records require the normal workflow.
                if (
                    model.startswith(("account.", "sale.", "purchase.", "stock."))
                    and "state" in target._fields
                    and target.state not in ("draft", "sent")
                ):
                    raise UserError(
                        self.env._("Document validé : intervention sensible à faire approuver.")
                    )
                before = json_value(target.read(sorted(values), load=None)[0])
                before.pop("id", None)
                if before != {k: False if v is None else v for k, v in expected.items()}:
                    raise UserError(self.env._("Valeurs modifiées ; relire avant de corriger."))
                target.with_context(mail_notify_noemail=True, mail_notify_force_send=False).write(
                    values
                )
            after = json_value(target.read(sorted(values), load=None)[0])
            after.pop("id", None)
            audit = (
                self.sudo()
                .with_context(mail_create_nosubscribe=True)
                .create(
                    {
                        "request_key": key,
                        "target_model": model,
                        "target_id": target.id,
                        "requester_id": actor.id,
                        "agent_id": self.env.uid,
                        "source_message_id": source.id,
                        "reason": reason.strip(),
                        "before_values": before,
                        "after_values": after,
                    }
                )
            )
            thread = (
                target
                if callable(getattr(target, "message_post", None))
                and "message_ids" in target._fields
                else audit
            )
            note = thread.with_context(
                mail_notify_noemail=True, mail_notify_force_send=False, mail_post_autofollow=False
            ).message_post(
                body=self._business_note(
                    "création" if creating else "correction", target, reason, before, after
                ),
                author_id=self.env.user.partner_id.id,
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
            if not note:
                raise UserError(self.env._("Journal obligatoire."))
            models.Model.write(audit, {"chatter_message_id": note.id})
            return audit._result()

    def _business_note(self, verb, target, reason, before, after):
        """Readable chatter note: title, motive, Field | Avant | Après table."""
        labels = {name: f"{field.string} ({name})" for name, field in target._fields.items()}
        return (
            Markup("<p><strong>Hermes N1 : %s sur %s #%s</strong></p>")
            % (verb, target._name, target.id)
            + Markup('<p class="mb-1"><strong>Motif</strong></p>')
            + agent_html(reason)
            + values_table(before, after, labels)
        )

    @api.model
    def agir_metier(
        self, model, record_id, action, expected, reason, channel_id, message_id, partner_id
    ):
        """Ordinary lifecycle actions, never arbitrary model method execution."""
        actor, source = self._business_actor(channel_id, message_id, partner_id)
        target_model = self._business(model, actor, writable=True)
        if action not in ("archive", "unarchive", "unlink"):
            raise UserError(self.env._("Action inconnue ; consulter explorer."))
        if type(record_id) is not int or record_id <= 0:
            raise UserError(self.env._("Identifiant positif requis."))
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise UserError(self.env._("Motif obligatoire."))
        if not isinstance(expected, dict) or not expected or "write_date" not in expected:
            raise UserError(
                self.env._("Relire write_date et les champs concernés avant cette action.")
            )
        expected = json_value(expected)
        available = self._business_fields(target_model)
        if not set(expected) <= set(available) or len(expected) > 40:
            raise UserError(self.env._("Champs précédents non autorisés."))
        key = hashlib.sha256(
            json.dumps(
                [self.env.uid, source.id, model, record_id, action, expected],
                sort_keys=True,
                allow_nan=False,
            ).encode()
        ).hexdigest()
        with self.env.cr.savepoint():
            self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", [int(key[:15], 16)])
            previous = self.sudo().search([("request_key", "=", key)], limit=1)
            if previous:
                return previous._result(replayed=True)
            target = target_model.browse(record_id).exists()
            if not target:
                raise UserError(self.env._("Objet absent."))
            target.check_access("read")
            target.check_access("unlink" if action == "unlink" else "write")
            self.env.cr.execute(
                sql.SQL("SELECT id FROM {} WHERE id = %s FOR UPDATE").format(
                    sql.Identifier(target._table)
                ),
                [record_id],
            )
            target.invalidate_recordset()
            before = json_value(target.read(sorted(expected), load=None)[0])
            before.pop("id", None)
            if before != expected:
                raise UserError(self.env._("Objet modifié ; relire avant cette action."))
            if action == "unlink":
                target.unlink()
                after = {"deleted": True}
            else:
                if "active" not in self._business_fields(target_model, writable=True):
                    raise UserError(self.env._("Cet objet ne peut pas être archivé."))
                target.with_context(mail_notify_noemail=True, mail_notify_force_send=False).write(
                    {"active": action == "unarchive"}
                )
                after = {"active": target.active}
            audit = (
                self.sudo()
                .with_context(mail_create_nosubscribe=True)
                .create(
                    {
                        "request_key": key,
                        "target_model": model,
                        "target_id": record_id,
                        "requester_id": actor.id,
                        "agent_id": self.env.uid,
                        "source_message_id": source.id,
                        "reason": reason.strip(),
                        "before_values": before,
                        "after_values": after,
                    }
                )
            )
            thread = target if action != "unlink" and "message_ids" in target._fields else audit
            note = thread.with_context(
                mail_notify_noemail=True, mail_notify_force_send=False, mail_post_autofollow=False
            ).message_post(
                body=self._business_note(
                    ACTION_LABELS[action], target_model.browse(record_id), reason, before, after
                ),
                author_id=self.env.user.partner_id.id,
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
            if not note:
                raise UserError(self.env._("Journal obligatoire."))
            models.Model.write(audit, {"chatter_message_id": note.id})
            return audit._result()
