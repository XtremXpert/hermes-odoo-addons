"""One-time authorization codes for the Hermes dashboards (OAuth 2 code flow with PKCE).

Odoo is the identity provider: a dashboard at /hermes/<level>/ sends the browser to
/hermes/sso/authorize, which requires an administrator's Odoo session; the dashboard
then exchanges the code server to server at /hermes/sso/token. No password and no
Odoo session ever reaches the dashboard.
"""

import base64
import hashlib
import secrets
from datetime import timedelta

from odoo import api
from odoo import fields
from odoo import models

LEVELS = ("n1", "n2", "n3")
CODE_TTL = timedelta(seconds=60)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def s256(verifier):
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


class HermesDashboardSsoCode(models.Model):
    _name = "hermes.dashboard.sso.code"
    _description = "Code de connexion à usage unique d'une interface Hermes"
    _log_access = True

    code_hash = fields.Char(required=True, index=True, readonly=True)
    user_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="cascade")
    level = fields.Selection([(lvl, lvl.upper()) for lvl in LEVELS], required=True, readonly=True)
    redirect_uri = fields.Char(required=True, readonly=True)
    code_challenge = fields.Char(required=True, readonly=True)
    expires_at = fields.Datetime(required=True, readonly=True)
    used = fields.Boolean(readonly=True)

    @api.model
    def _issue(self, user, level, redirect_uri, code_challenge):
        code = secrets.token_urlsafe(32)
        self.sudo().create(
            {
                "code_hash": digest(code),
                "user_id": user.id,
                "level": level,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "expires_at": fields.Datetime.now() + CODE_TTL,
            }
        )
        return code

    @api.model
    def _redeem(self, code, verifier, level, redirect_uri):
        """The identity behind a valid code, or None. A code works once, even if refused."""
        if not all(isinstance(v, str) and v for v in (code, verifier, level, redirect_uri)):
            return None
        record = self.sudo().search([("code_hash", "=", digest(code))], limit=1)
        if not record or record.used:
            return None
        record.write({"used": True})
        user = record.user_id
        if (
            record.expires_at < fields.Datetime.now()
            or record.level != level
            or record.redirect_uri != redirect_uri
            or not secrets.compare_digest(record.code_challenge, s256(verifier))
            or not user.active
            or user.share
            or not user.has_group("base.group_system")
        ):
            return None
        return {
            "user_id": user.id,
            "login": user.login,
            "name": user.name,
            "email": user.email or "",
        }

    @api.autovacuum
    def _gc_expired(self):
        self.sudo().search(
            [("expires_at", "<", fields.Datetime.now() - timedelta(hours=1))]
        ).unlink()
