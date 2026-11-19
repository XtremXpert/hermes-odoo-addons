# Part of the sms_voipms Odoo module. See LICENSE for details.
"""Public endpoint receiving the SMS that VoIP.ms forwards to our DID."""

import logging
import secrets

from odoo import fields
from odoo.http import Controller
from odoo.http import request
from odoo.http import route

_logger = logging.getLogger(__name__)


class SmsVoipmsController(Controller):
    @route(
        "/sms_voipms/inbound/<string:token>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def inbound(self, token, **kwargs):
        """Handle one inbound SMS forwarded by the VoIP.ms URL callback.

        VoIP.ms replaces ``{FROM}``, ``{TO}`` and ``{MESSAGE}`` in the
        configured URL and calls it with GET. The token in the path is the
        only authentication (the provider does not sign the call).
        """
        expected = request.env["ir.config_parameter"].sudo().get_str("sms_voipms.inbound_token")
        if not expected or not secrets.compare_digest(token, expected):
            raise request.not_found()
        received_at = False
        timestamp = request.params.get("timestamp") or request.params.get("date")
        if timestamp:
            try:
                received_at = fields.Datetime.to_datetime(timestamp)
            except (TypeError, ValueError):
                received_at = False
        try:
            request.env["voipms.sms.inbound"].sudo()._process_incoming(
                request.params.get("from") or "",
                request.params.get("to") or "",
                request.params.get("message") or "",
                provider_id=request.params.get("id") or False,
                received_at=received_at,
            )
        except Exception:
            # A retry every 30 minutes would only repeat the same failure.
            _logger.exception("SMS VoIP.ms : échec du traitement d'un message entrant.")
        return request.make_response("ok", headers=[("Content-Type", "text/plain; charset=utf-8")])
