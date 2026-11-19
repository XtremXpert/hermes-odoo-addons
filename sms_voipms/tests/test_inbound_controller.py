# Part of the sms_voipms Odoo module. See LICENSE for details.

from odoo.tests import HttpCase
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestInboundController(HttpCase):
    @classmethod
    def setUpClass(cls):
        """Commit the inbound token so the HTTP request sees it."""
        super().setUpClass()
        cls.token = "inbound-test-token"
        cls.env["ir.config_parameter"].sudo().set_str("sms_voipms.inbound_token", cls.token)
        cls.env.flush_all()

    def test_valid_token_returns_ok_and_processes(self):
        """A valid token processes the message and answers ok."""
        response = self.url_open(
            "/sms_voipms/inbound/%s?from=4184541752&to=14184803381&message=Bonjour" % self.token
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text.strip(), "ok")
        self.assertTrue(self.env["voipms.sms.inbound"].sudo().search([("body", "=", "Bonjour")]))

    def test_wrong_token_returns_404_without_writing(self):
        """A wrong token is rejected with 404 and writes nothing."""
        response = self.url_open(
            "/sms_voipms/inbound/wrong?from=4184541752&to=14184803381&message=Bonjour"
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.env["voipms.sms.inbound"].sudo().search([]))
