# Part of the sms_voipms Odoo module. See LICENSE for details.

from odoo.tests import TransactionCase

from .common import SmsVoipmsCommon


class TestInbound(SmsVoipmsCommon, TransactionCase):
    def _inbound(self, body, number="4184541752"):
        """Process one inbound SMS the way the controller does."""
        return (
            self.env["voipms.sms.inbound"]
            .sudo()
            ._process_incoming(number, "14184803381", body, provider_id="p1")
        )

    def test_stop_adds_blacklist_without_reply(self):
        """A STOP keyword only feeds the phone blacklist."""
        self._inbound("STOP")
        blacklist = self.env["phone.blacklist"].sudo().search([("number", "=", "+14184541752")])
        self.assertTrue(blacklist)
        self.assertFalse(self.env["voipms.sms.inbound"].search([]))
        self.assertFalse(self.env["sms.sms"].search([]))

    def test_stop_is_case_insensitive_and_trimmed(self):
        """A lower-case STOP with spaces is still a STOP."""
        self._inbound("  arrete  ")
        self.assertTrue(
            self.env["phone.blacklist"].sudo().search([("number", "=", "+14184541752")])
        )

    def test_reply_posts_on_origin_record(self):
        """A reply to a recent outgoing SMS lands in the origin chatter."""
        partner_from = self.env["res.partner"].create(
            {
                "name": "Client",
                "phone": "418-454-1752",
                "country_id": self.env.ref("base.ca").id,
            }
        )
        origin = self.env["res.partner"].create({"name": "Origine"})
        out_message = origin.message_post(body="Bonjour", message_type="comment")
        self.env["sms.sms"].create(
            {
                "number": "4184541752",
                "body": "Bonjour",
                "mail_message_id": out_message.id,
                "record_company_id": self.company.id,
                "state": "pending",
            }
        )
        record = self._inbound("Ma réponse")
        self.assertEqual(record.state, "done")
        self.assertEqual(record.partner_id, partner_from)
        reply = origin.message_ids.filtered(
            lambda message: message.message_type == "sms" and "Ma réponse" in (message.body or "")
        )
        self.assertTrue(reply)
        self.assertEqual(reply.author_id, partner_from)

    def test_reply_queued_when_unmatched(self):
        """An unmatched reply is queued, not posted anywhere."""
        record = self._inbound("Bonjour")
        self.assertEqual(record.state, "new")
        self.assertFalse(record.partner_id)
        self.assertEqual(record.from_number, "14184541752")

    def test_known_contact_without_outgoing_is_queued(self):
        """A known contact without a recent send stays in the queue."""
        partner = self.env["res.partner"].create(
            {
                "name": "Client",
                "phone": "418-454-1752",
                "country_id": self.env.ref("base.ca").id,
            }
        )
        record = self._inbound("Bonjour")
        self.assertEqual(record.state, "new")
        self.assertEqual(record.partner_id, partner)
