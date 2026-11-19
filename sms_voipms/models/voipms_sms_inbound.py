# Part of the sms_voipms Odoo module. See LICENSE for details.
"""Inbound SMS received from the VoIP.ms ``url_callback``."""

import logging
from datetime import timedelta

from odoo import api
from odoo import fields
from odoo import models
from odoo.addons.voipms_sms.services.sms_segmentation import normalize_nanp

_logger = logging.getLogger(__name__)

STOP_KEYWORDS = {
    "STOP",
    "STOPALL",
    "ARRET",
    "ARRETE",
    "ARRETER",
    "UNSUBSCRIBE",
    "DESABONNER",
    "DESABONNE",
}
LOOKBACK_DAYS = 90


class VoIPMSSmsInbound(models.Model):
    _name = "voipms.sms.inbound"
    _description = "VoIP.ms : SMS reçu"
    _order = "received_at desc, id desc"

    from_number = fields.Char(string="Expéditeur", required=True, index=True)
    to_number = fields.Char(string="DID destinataire", index=True)
    body = fields.Text(string="Message", required=True)
    provider_id = fields.Char(string="ID VoIP.ms", index=True)
    received_at = fields.Datetime(string="Reçu le", default=fields.Datetime.now)
    state = fields.Selection(
        [("new", "Nouveau"), ("done", "Traité"), ("ignored", "Ignoré")],
        string="État",
        default="new",
        required=True,
    )
    partner_id = fields.Many2one("res.partner", string="Contact", ondelete="set null")
    mail_message_id = fields.Many2one(
        "mail.message", string="Message d'origine", ondelete="set null"
    )

    def action_done(self):
        """Mark the inbound message as handled."""
        self.write({"state": "done"})

    def action_ignored(self):
        """Mark the inbound message as ignored."""
        self.write({"state": "ignored"})

    @api.model
    def _find_partner(self, number):
        """Return the contact whose sanitized phone matches ``number``."""
        return (
            self.env["res.partner"]
            .sudo()
            .search([("phone_sanitized", "in", [number, "+" + number])], limit=1)
        )

    @api.model
    def _post_reply(self, number, body, partner):
        """Post the reply on the record the last outgoing SMS came from."""
        sms = (
            self.env["sms.sms"]
            .sudo()
            .search(
                [
                    ("number", "in", (number, number[1:])),
                    (
                        "create_date",
                        ">=",
                        fields.Datetime.now() - timedelta(days=LOOKBACK_DAYS),
                    ),
                    ("state", "in", ("pending", "sent")),
                ],
                order="id desc",
                limit=1,
            )
        )
        message = sms.mail_message_id
        if not message or not message.model or not message.res_id:
            return self.env["mail.message"]
        record = self.env[message.model].sudo().browse(message.res_id)
        if not record.exists() or not hasattr(record, "message_post"):
            return self.env["mail.message"]
        author = partner or self.env.ref("base.partner_root")
        return record.message_post(
            body=body if partner else "%s : %s" % (number, body),
            message_type="sms",
            author_id=author.id,
            subtype_xmlid="mail.mt_comment",
        )

    @api.model
    def _process_incoming(self, from_number, to_number, body, provider_id=None, received_at=None):
        """Process one inbound SMS; return the queue record it created.

        STOP keywords only feed ``phone.blacklist`` (Odoo behaviour): the mass
        composer filters those numbers, manual sends are not blocked.
        """
        try:
            number = normalize_nanp(from_number)
        except ValueError:
            _logger.warning("SMS VoIP.ms : expéditeur hors NANP ignoré.")
            return self.browse()
        body = (body or "").strip()
        if not body:
            return self.browse()
        destination = (to_number or "").strip()
        if destination:
            try:
                destination = normalize_nanp(destination)
            except ValueError:
                _logger.info("SMS VoIP.ms : DID destinataire hors NANP laissé tel quel.")
        else:
            destination = False
        if body.upper() in STOP_KEYWORDS:
            self.env["phone.blacklist"].sudo().create({"number": "+" + number})
            return self.browse()
        partner = self._find_partner(number)
        message = self._post_reply(number, body, partner)
        return self.create(
            {
                "from_number": number,
                "to_number": destination,
                "body": body,
                "provider_id": provider_id or False,
                "received_at": received_at or fields.Datetime.now(),
                "partner_id": partner.id if partner else False,
                "mail_message_id": message.id if message else False,
                "state": "done" if message else "new",
            }
        )
