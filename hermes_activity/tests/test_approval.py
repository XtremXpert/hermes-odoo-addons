import re

from odoo.tests import HttpCase
from odoo.tests import JsonRpcException
from odoo.tests import tagged

INVITE = (
    "Commande à approuver.\n\n"
    "Reply `/approve` to execute, `/approve session` to approve this pattern for the "
    "session, `/approve always` to approve permanently, or `/deny` to cancel."
)


@tagged("post_install", "-at_install")
class TestApproval(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("base.user_admin")
        cls.bot = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Hermes approbation",
                    "login": "approval-test",
                    "group_ids": [
                        (
                            6,
                            0,
                            [
                                cls.env.ref("base.group_user").id,
                                cls.env.ref("hermes_n1_audit.group_agent").id,
                            ],
                        )
                    ],
                }
            )
        )
        cls.channel = (
            cls.env["discuss.channel"]
            .with_user(cls.admin)
            ._get_or_create_chat([cls.bot.partner_id.id])
        )
        cls.other = cls.env["discuss.channel"].create(
            {"name": "Sans admin", "channel_type": "channel"}
        )
        cls.other.channel_member_ids.filtered(
            lambda m: m.partner_id == cls.admin.partner_id
        ).unlink()

    def _messages(self, channel=None):
        return self.env["mail.message"].search_count(
            [("model", "=", "discuss.channel"), ("res_id", "=", (channel or self.channel).id)]
        )

    def test_agent_invite_becomes_relative_buttons(self):
        message = self.channel.with_user(self.bot).message_post(
            body=INVITE, message_type="comment", subtype_xmlid="mail.mt_comment"
        )
        body = str(message.body)
        self.assertIn("Commande à approuver.", body)
        self.assertNotIn("Reply", body)
        self.assertEqual(body.count("o_hermes_approve"), 4)
        self.assertIn('class="btn btn-success', body)
        self.assertIn(
            'href="/hermes/repondre?canal=%d&amp;cmd=%%2Fapprove"' % self.channel.id, body
        )
        self.assertIn("<code>/approve</code>", body)

    def test_get_only_shows_a_confirmation(self):
        self.authenticate("admin", "admin")
        avant = self._messages()
        url = "/hermes/repondre?canal=%d&cmd=%%2Fapprove" % self.channel.id
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="csrf_token"', response.text.replace("'", '"'))
        self.assertEqual(self._messages(), avant, "un GET ne doit rien poster")

    def test_unknown_command_or_foreign_channel_is_not_found(self):
        self.authenticate("admin", "admin")
        for url in (
            "/hermes/repondre?canal=%d&cmd=bonjour" % self.channel.id,
            "/hermes/repondre?canal=%d&cmd=%%2Fapprove" % self.other.id,
            "/hermes/repondre?canal=x&cmd=%2Fapprove",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.url_open(url).status_code, 404)

    def test_post_requires_the_csrf_token(self):
        self.authenticate("admin", "admin")
        avant = self._messages()
        with self.assertLogs("odoo.http", "WARNING"):
            response = self.url_open(
                "/hermes/repondre",
                data={"canal": self.channel.id, "cmd": "/approve"},
                allow_redirects=False,
            )
        self.assertNotIn(response.status_code, (200, 303))
        self.assertEqual(self._messages(), avant)

    def test_confirmed_post_is_signed_by_the_clicker(self):
        self.authenticate("admin", "admin")
        page = self.url_open("/hermes/repondre?canal=%d&cmd=%%2Fdeny" % self.channel.id).text
        jeton = re.search(r"name=.csrf_token. value=.([^'\"]+)", page).group(1)
        response = self.url_open(
            "/hermes/repondre",
            data={"canal": self.channel.id, "cmd": "/deny", "csrf_token": jeton},
            allow_redirects=False,
        )
        self.assertIn(response.status_code, (302, 303))
        dernier = self.env["mail.message"].search(
            [("model", "=", "discuss.channel"), ("res_id", "=", self.channel.id)], limit=1
        )
        self.assertEqual(dernier.author_id, self.admin.partner_id)
        self.assertIn("/deny", str(dernier.body))

    def test_jsonrpc_click_posts_as_the_clicker(self):
        self.authenticate("admin", "admin")
        resultat = self.make_jsonrpc_request(
            "/hermes/approbation", {"canal": self.channel.id, "cmd": "/approve"}
        )
        message = self.env["mail.message"].browse(resultat["message_id"])
        self.assertEqual(message.author_id, self.admin.partner_id)
        self.assertIn("/approve", str(message.body))
        avant = self._messages(self.other)
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request(
                "/hermes/approbation", {"canal": self.other.id, "cmd": "/approve"}
            )
        self.assertEqual(self._messages(self.other), avant)
