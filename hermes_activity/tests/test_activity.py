from datetime import timedelta
from unittest.mock import patch

from markupsafe import Markup

from odoo import fields
from odoo.exceptions import AccessError
from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestActivity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("base.user_admin")
        cls.bot = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Hermes test",
                    "login": "activity-test",
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
        cls.message = cls.channel.with_user(cls.admin).message_post(
            body="Test", message_type="comment", subtype_xmlid="mail.mt_comment"
        )
        cls.source = {
            "channel_id": cls.channel.id,
            "message_id": cls.message.id,
            "partner_id": cls.admin.partner_id.id,
        }
        cls.service = cls.env["hermes.activity"].with_user(cls.bot)

    def test_gateway_poll_marks_only_the_authenticated_agent_online(self):
        for group_name in (
            "hermes_n1_audit.group_agent",
            "hermes_n2_support.group_agent",
            "hermes_n3_infra.group_agent",
        ):
            group = self.env.ref(group_name, raise_if_not_found=False)
            if not group:
                continue
            with self.subTest(group=group_name):
                self.bot.write(
                    {"group_ids": [(6, 0, [self.env.ref("base.group_user").id, group.id])]}
                )
                self.bot.presence_ids.unlink()
                self.env["discuss.channel.member"].with_user(self.bot).search_read(
                    [("partner_id", "=", self.bot.partner_id.id)], fields=["channel_id"]
                )
                self.assertEqual(self.bot.im_status, "online")
                self.assertEqual(self.bot.presence_ids.user_id, self.bot)
        self.admin.presence_ids.unlink()
        self.env["discuss.channel.member"].with_user(self.admin).search_read(
            [("partner_id", "=", self.bot.partner_id.id)], fields=["channel_id"]
        )
        self.assertFalse(self.admin.presence_ids)

    def test_agent_presence_expires_and_recovers_without_expiring_humans(self):
        self.service._heartbeat()
        self.env["mail.presence"]._update_presence(self.admin)
        old = fields.Datetime.now() - timedelta(minutes=4)
        self.bot.presence_ids.write({"last_poll": old})
        self.admin.presence_ids.write({"last_poll": old})
        self.env["hermes.activity"]._expire_presence()
        self.assertEqual(self.bot.im_status, "offline")
        self.assertEqual(self.admin.im_status, "online")
        self.service._heartbeat()
        self.env["hermes.activity"]._expire_presence()
        self.assertEqual(self.bot.im_status, "online")

    def test_activity_keeps_the_agent_online_during_work(self):
        self.bot.presence_ids.unlink()
        self.service.publier(**self.source, sequence=1, state="working")
        self.assertEqual(self.bot.im_status, "online")

    def test_step_history_heartbeat_terminal_and_new_request(self):
        with patch("odoo.addons.hermes_activity.models.activity.time.time", return_value=100):
            self.service.publier(**self.source, sequence=1, state="working")
        with patch("odoo.addons.hermes_activity.models.activity.time.time", return_value=103):
            self.service.publier(**self.source, sequence=2, state="working")
        self.assertEqual(len(self.service.lire(self.channel.id)["steps"]), 1)
        with patch("odoo.addons.hermes_activity.models.activity.time.time", return_value=105):
            self.service.publier(**self.source, sequence=3, state="tool", tool="chercher")
        with patch("odoo.addons.hermes_activity.models.activity.time.time", return_value=110):
            self.service.publier(**self.source, sequence=4, state="done")
        activity = self.service.lire(self.channel.id)
        self.assertEqual(
            [step["label"] for step in activity["steps"]],
            ["Analyse de la demande", "Recherche dans Odoo", "Traitement terminé"],
        )
        self.assertEqual(activity["steps"][0]["ended_at"], 105)
        self.assertEqual(activity["steps"][1]["ended_at"], 110)
        self.assertFalse(
            self.service.publier(**self.source, sequence=5, state="working")["accepted"]
        )
        self.assertEqual(self.service.lire(self.channel.id), activity)
        message = self.channel.with_user(self.admin).message_post(
            body="Suite", message_type="comment"
        )
        source = dict(self.source, message_id=message.id)
        self.service.publier(**source, sequence=1, state="working")
        fresh = self.service.lire(self.channel.id)
        self.assertEqual(fresh["step_count"], 1)
        self.assertEqual(len(fresh["steps"]), 1)

    def test_step_history_is_bounded(self):
        for sequence in range(1, 57):
            self.service.publier(
                **self.source,
                sequence=sequence,
                state="tool",
                tool="chercher" if sequence % 2 else "compter",
            )
        activity = self.service.lire(self.channel.id)
        self.assertEqual(activity["step_count"], 56)
        self.assertEqual(len(activity["steps"]), 50)
        self.assertEqual(activity["steps"][0]["number"], 7)

    def test_status_is_private_ordered_and_terminal(self):
        self.assertTrue(
            self.service.publier(**self.source, sequence=1, state="working")["accepted"]
        )
        self.assertTrue(
            self.service.publier(**self.source, sequence=3, state="tool", tool="chercher")[
                "accepted"
            ]
        )
        self.assertFalse(
            self.service.publier(**self.source, sequence=2, state="working")["accepted"]
        )
        self.service.publier(**self.source, sequence=4, state="done")
        self.assertFalse(
            self.service.publier(**self.source, sequence=5, state="working")["accepted"]
        )
        self.assertEqual(
            self.env["hermes.activity"].with_user(self.admin).lire(self.channel.id)["state"], "done"
        )
        outsider = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create({"name": "Other", "login": "activity-other"})
        )
        with self.assertRaises(AccessError):
            self.env["hermes.activity"].with_user(outsider).lire(self.channel.id)
        with self.assertRaises(AccessError):
            self.env["hermes.activity"].with_user(self.admin).publier(
                **self.source, sequence=6, state="done"
            )
        with self.assertRaises(AccessError):
            self.channel.with_user(self.bot).write({"hermes_activity_state": {}})
        with self.assertRaises(UserError):
            self.service.publier(
                **self.source, sequence=6, state="tool", tool="raw private content"
            )

    def test_formatted_reply_is_authored_by_bot_and_safe(self):
        text = '# Résultat\n\n**Oui**\n\n- premier\n- second\n\n```\nprint("test")\n```\n<script>alert(1)</script>\n[x](https://example.org/"onmouseover="bad)'
        mid = self.service.repondre(**self.source, text=text)
        message = self.env["mail.message"].browse(mid)
        self.assertEqual(message.author_id, self.bot.partner_id)
        self.assertEqual(message.res_id, self.channel.id)
        body = str(message.body)
        for markup in ["<strong>Oui</strong>", "<li>premier</li>", "<pre>"]:
            self.assertIn(markup, body)
        self.assertNotIn("<script>", body)
        self.assertNotIn('" onmouseover=', body)
        with self.assertRaises(AccessError):
            self.service.repondre(
                **dict(self.source, partner_id=self.bot.partner_id.id), text="spoof"
            )

    def test_rpc_markdown_is_formatted_for_each_agent_level(self):
        text = (
            "# Résultat\n\n**Oui** et `code`\n\n- premier\n- second\n\n"
            "| Service | État |\n| --- | --- |\n| Odoo | Prêt |\n\n"
            "```\n<strong>code littéral</strong>\n```\n\n"
            "<script>alert(1)</script>\n[x](javascript:alert(1))"
        )
        for group_name in (
            "hermes_n1_audit.group_agent",
            "hermes_n2_support.group_agent",
            "hermes_n3_infra.group_agent",
        ):
            group = self.env.ref(group_name, raise_if_not_found=False)
            if not group:
                continue
            with self.subTest(group=group_name):
                self.bot.write(
                    {"group_ids": [(6, 0, [self.env.ref("base.group_user").id, group.id])]}
                )
                message = self.channel.with_user(self.bot).message_post(
                    body=text, message_type="comment", subtype_xmlid="mail.mt_comment"
                )
                self.assertEqual(message.author_id, self.bot.partner_id)
                self.assertEqual(message.res_id, self.channel.id)
                body = str(message.body)
                for markup in (
                    "<h3>",
                    "<strong>Oui</strong>",
                    "<code>code</code>",
                    "<li>premier</li>",
                    "<table ",
                    "<td>Prêt</td>",
                    "<pre>",
                ):
                    self.assertIn(markup, body)
                self.assertNotIn("<script>", body)
                self.assertNotIn('href="javascript:', body)
                self.assertIn("&lt;strong&gt;code littéral&lt;/strong&gt;", body)

    def test_human_plain_text_and_existing_html_are_preserved(self):
        message = self.channel.with_user(self.admin).message_post(
            body="**Texte humain**", message_type="comment"
        )
        self.assertIn("**Texte humain**", str(message.body))
        message = self.channel.with_user(self.bot).message_post(
            body=Markup("<p><strong>Déjà formaté</strong></p>"), message_type="comment"
        )
        self.assertIn("<strong>Déjà formaté</strong>", str(message.body))
        self.assertNotIn("&lt;strong&gt;", str(message.body))
