# Copyright (C) 2026 Bemade Inc.
# Copyright (C) 2026 Benoît Vézina, Diverse-Cité
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""HTTP controller exposing the token-authenticated mail-push endpoint.

Three routes, all under ``/diverse/mail-gateway/`` :

- ``GET  /health``  — unauthenticated liveness probe.
- ``POST /check``   — authenticated no-op for client-side smoke tests.
- ``POST /process`` — the real thing: validate token, call
  ``mail.thread.message_process`` as SUPERUSER on the parsed body.

Auth is the responsibility of this controller alone. Routes use
``auth='none'`` so Odoo doesn't try to materialise a user session
(which would fail for `auth='public'` since we want zero user identity
involvement, by design — the trust anchor is the token).
"""

import json
import logging
from email import message_from_bytes

from odoo import SUPERUSER_ID
from odoo import http
from odoo import models
from odoo.http import Response
from odoo.http import request

_logger = logging.getLogger(__name__)

# Hard-coded fallback if ir.module.module lookup fails (it shouldn't,
# but the health endpoint must always answer 200).
_FALLBACK_MODULE_VERSION = "20.0.1.0.0"

# Header names — kept as constants so tests can reference them.
H_TOKEN = "X-Mail-Gateway-Token"
H_SAVE_ORIGINAL = "X-Mail-Gateway-Save-Original"
H_STRIP_ATTACHMENTS = "X-Mail-Gateway-Strip-Attachments"

# Setting key (ir.config_parameter). When True, allows HTTP (no TLS).
# Default: False → endpoint refuses non-HTTPS requests.
PARAM_ALLOW_HTTP = "diverse_mail_gateway.allow_http"


def _json_response(body: dict, status: int = 200) -> Response:
    """Standard JSON response envelope."""
    return Response(
        json.dumps(body),
        status=status,
        content_type="application/json; charset=utf-8",
    )


def _is_truthy_param(value) -> bool:
    """Parse the catch-all 'is this truthy?' for header values & config params."""
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class MailGatewayController(http.Controller):
    # ---- Health ----------------------------------------------------------

    @http.route(
        "/diverse/mail-gateway/health",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def health(self) -> Response:
        """Liveness probe. No auth, no side-effect, always 200."""
        try:
            module = (
                request.env["ir.module.module"]
                .sudo()
                .search([("name", "=", "diverse_mail_gateway")], limit=1)
            )
            mod_version = module.installed_version or _FALLBACK_MODULE_VERSION
        except Exception:  # noqa: BLE001 — the health probe must always answer 200
            mod_version = _FALLBACK_MODULE_VERSION

        try:
            from odoo.release import version_info

            odoo_version = ".".join(str(x) for x in version_info[:3])
        except Exception:  # noqa: BLE001 — the health probe must always answer 200
            odoo_version = "unknown"

        return _json_response(
            {"ok": True, "module_version": mod_version, "odoo_version": odoo_version},
            status=200,
        )

    # ---- Check (auth-only smoke test) ------------------------------------

    @http.route(
        "/diverse/mail-gateway/check",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
        readonly=False,
    )
    def check(self) -> Response:
        """Validate the token without doing any work. Useful for clients
        to verify their credential after rotation."""
        if not self._tls_check_passes():
            return _json_response(
                {"ok": False, "error": "forbidden", "detail": "HTTPS required"},
                status=403,
            )
        token_rec = self._validate_token_header()
        if not token_rec:
            return _json_response({"ok": False, "error": "unauthorized"}, status=401)
        return _json_response({"ok": True, "token_label": token_rec.name}, status=200)

    # ---- Process (the real endpoint) -------------------------------------

    @http.route(
        "/diverse/mail-gateway/process",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
        readonly=False,
    )
    def process(self) -> Response:
        if not self._tls_check_passes():
            return _json_response(
                {"ok": False, "error": "forbidden", "detail": "HTTPS required"},
                status=403,
            )

        token_rec = self._validate_token_header()
        if not token_rec:
            return _json_response({"ok": False, "error": "unauthorized"}, status=401)

        # Body — bytes preferred (RFC 5322 doesn't really fit one
        # encoding, latin-1 round-trips losslessly to str).
        raw = request.httprequest.get_data() or b""
        if not raw:
            return _json_response(
                {"ok": False, "error": "bad_request", "detail": "empty body"},
                status=400,
            )

        headers = request.httprequest.headers
        kwargs = {
            "save_original": _is_truthy_param(headers.get(H_SAVE_ORIGINAL)),
            "strip_attachments": _is_truthy_param(headers.get(H_STRIP_ATTACHMENTS)),
        }

        message_id = self._best_effort_message_id(raw)
        log_ctx = {
            "token_label": token_rec.name,
            "message_id": message_id,
            "ip": request.httprequest.remote_addr,
        }

        # The actual elevation. Trust is anchored in the token validation
        # above; from here on we run as SUPERUSER scoped to one method
        # call.
        try:
            result = request.env(user=SUPERUSER_ID)["mail.thread"].message_process(
                None, raw, **kwargs
            )
        except ValueError as exc:
            err_msg = str(exc)
            # Odoo raises a generic ValueError for "No possible route found
            # for incoming message …". Treat that as a routing miss (422)
            # rather than internal error (500), so the LMTP gateway can
            # decide to bounce or hold appropriately.
            if "no possible route" in err_msg.lower():
                _logger.info(
                    "mail_gateway_no_route token=%s message_id=%s ip=%s",
                    log_ctx["token_label"],
                    log_ctx["message_id"],
                    log_ctx["ip"],
                )
                return _json_response(
                    {"ok": False, "error": "no_route", "detail": err_msg},
                    status=422,
                )
            _logger.warning(
                "mail_gateway_bad_request token=%s message_id=%s err=%s",
                log_ctx["token_label"],
                log_ctx["message_id"],
                err_msg,
            )
            return _json_response(
                {"ok": False, "error": "bad_request", "detail": err_msg},
                status=400,
            )
        except Exception as exc:
            _logger.exception(
                "mail_gateway_internal_error token=%s message_id=%s",
                log_ctx["token_label"],
                log_ctx["message_id"],
            )
            return _json_response(
                {"ok": False, "error": "internal", "detail": str(exc)[:300]},
                status=500,
            )

        # message_process returns False when no route was found but a module
        # (e.g. mail_manual_routing) silently swallowed the message instead of
        # raising ValueError. Treat it the same as the ValueError no-route path
        # so the LMTP relay knows the delivery did not land on a real thread.
        if not result:
            _logger.info(
                "mail_gateway_no_route token=%s message_id=%s ip=%s",
                log_ctx["token_label"],
                log_ctx["message_id"],
                log_ctx["ip"],
            )
            return _json_response(
                {"ok": False, "error": "no_route", "detail": "message_process returned no result"},
                status=422,
            )

        # Odoo 20 returns the thread record, older series its id: the JSON
        # contract stays the id.
        if isinstance(result, models.BaseModel):
            result = result.id

        _logger.info(
            "mail_gateway_delivered token=%s message_id=%s result=%s ip=%s",
            log_ctx["token_label"],
            log_ctx["message_id"],
            result,
            log_ctx["ip"],
        )
        return _json_response(
            {"ok": True, "result": result, "message_id": message_id},
            status=200,
        )

    # ---- Internals -------------------------------------------------------

    def _validate_token_header(self):
        """Read X-Mail-Gateway-Token, validate it, return the record or empty."""
        raw_token = request.httprequest.headers.get(H_TOKEN, "")
        ip = request.httprequest.remote_addr or ""
        Token = request.env["diverse.mail_gateway.token"].sudo()
        return Token.validate_token(raw_token, ip=ip)

    def _tls_check_passes(self) -> bool:
        """Reject HTTP unless the operator opted in via ir.config_parameter."""
        if request.httprequest.is_secure:
            return True
        # Odoo behind a TLS-terminating proxy: trust X-Forwarded-Proto if
        # set (Werkzeug already honours it when TRUSTED_PROXIES is set in
        # Odoo's `--proxy-mode`).
        ICP = request.env["ir.config_parameter"].sudo()
        return _is_truthy_param(ICP.get_str(PARAM_ALLOW_HTTP, "False"))

    @staticmethod
    def _best_effort_message_id(raw: bytes | str) -> str:
        """Parse the Message-Id for log correlation. Never raises."""
        try:
            if isinstance(raw, str):
                raw = raw.encode("latin-1", errors="replace")
            msg = message_from_bytes(raw)
            value = msg.get("Message-Id", "")
            return value.strip() if isinstance(value, str) else ""
        except Exception:  # noqa: BLE001 — log correlation only, never raises
            return ""
