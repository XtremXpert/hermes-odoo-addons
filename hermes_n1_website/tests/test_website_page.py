from odoo.exceptions import AccessError
from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests import tagged

from ..models.website_page import sanitize

BODY = '<section class="s_text_block"><div class="container"><p>Avant</p></div></section>'


@tagged("post_install", "-at_install")
class TestN1WebsitePage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("base.user_admin")
        cls.bot = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "N1 web bot",
                    "login": "n1_web_test_bot",
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
            body="Mets à jour le texte de la page.",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        cls.website = cls.env["website"].search([], order="id", limit=1)
        view = cls.env["ir.ui.view"].create(
            {
                "name": "Page de test N1",
                "type": "qweb",
                "key": "hermes_n1_website.test_page",
                "arch": '<t t-name="hermes_n1_website.test_page"><t t-call="website.layout">'
                f'<div id="wrap" class="oe_structure">{BODY}</div></t></t>',
            }
        )
        cls.page = cls.env["website.page"].create(
            {"url": "/n1-test-page", "view_id": view.id, "website_id": cls.website.id}
        )
        cls.service = cls.env["hermes.n1.change"].with_user(cls.bot)

    def source(self):
        return {
            "channel_id": self.channel.id,
            "message_id": self.message.id,
            "partner_id": self.admin.partner_id.id,
        }

    def read_page(self):
        return self.service.lire_page_web(self.page.id, **self.source())

    def test_read_then_write_replaces_only_the_wrap_and_is_traced(self):
        current = self.read_page()
        self.assertIn("<p>Avant</p>", current["html"])
        self.assertTrue(current["modifiable"])
        result = self.service.modifier_page_web(
            self.page.id,
            '<section class="s_text_block"><p>Après</p></section>',
            current["sha256"],
            "Texte mis à jour",
            **self.source(),
        )
        after = self.read_page()
        self.assertIn("<p>Après</p>", after["html"])
        self.assertNotIn("Avant", after["html"])
        self.assertEqual(result["sha256"], after["sha256"])
        audit = self.env["hermes.n1.change"].browse(result["audit_id"])
        self.assertEqual(
            (audit.target_model, audit.target_id, audit.requester_id),
            ("website.page", self.page.id, self.admin),
        )
        self.assertIn("Avant", audit.before_values["html"])
        self.assertTrue(audit.chatter_message_id)
        again = self.service.modifier_page_web(
            self.page.id,
            '<section class="s_text_block"><p>Après</p></section>',
            current["sha256"],
            "Texte mis à jour",
            **self.source(),
        )
        self.assertTrue(again["deja_applique"])

    def test_html_is_sanitized_to_plain_content(self):
        dirty = (
            '<p onclick="x()" t-att-class="1">Texte<script>alert(1)</script></p>'
            '<t t-out="request.env.user.login"/><a href="javascript:alert(1)">lien</a>'
            '<span data-oe-model="res.partner" data-oe-id="1" data-oe-field="name">Nom</span>'
            '<iframe src="https://example.com"></iframe><form action="/x"><input name="a"/></form>'
            '<img src="data:image/png;base64,AAAA" alt="ok"/>'
        )
        clean = sanitize(dirty)
        for forbidden in (
            "script",
            "onclick",
            "t-att",
            "t-out",
            "javascript:",
            "data-oe-",
            "iframe",
            "<form",
            "<input",
        ):
            self.assertNotIn(forbidden, clean)
        self.assertIn("Texte", clean)
        self.assertIn("Nom", clean)
        self.assertIn('src="data:image/png', clean)

    def test_stale_hash_qweb_section_and_unauthorized_requester_are_refused(self):
        with self.assertRaises(UserError):
            self.service.modifier_page_web(
                self.page.id, "<p>x</p>", "0" * 64, "Motif", **self.source()
            )
        dynamic = self.env["ir.ui.view"].create(
            {
                "name": "Page dynamique",
                "type": "qweb",
                "key": "hermes_n1_website.dynamic_page",
                "arch": '<t t-name="hermes_n1_website.dynamic_page"><t t-call="website.layout">'
                '<div id="wrap"><p t-out="request.env.user.name"/></div></t></t>',
            }
        )
        page = self.env["website.page"].create(
            {"url": "/n1-dynamic", "view_id": dynamic.id, "website_id": self.website.id}
        )
        read = self.service.lire_page_web(page.id, **self.source())
        self.assertFalse(read["modifiable"])
        with self.assertRaises(UserError):
            self.service.modifier_page_web(
                page.id, "<p>x</p>", read["sha256"], "Motif", **self.source()
            )
        with_form = self.env["ir.ui.view"].create(
            {
                "name": "Page avec formulaire",
                "type": "qweb",
                "key": "hermes_n1_website.form_page",
                "arch": '<t t-name="hermes_n1_website.form_page"><t t-call="website.layout">'
                '<div id="wrap"><section><form action="/website/form/"><input name="email"/></form></section></div></t></t>',
            }
        )
        page = self.env["website.page"].create(
            {"url": "/n1-form", "view_id": with_form.id, "website_id": self.website.id}
        )
        read = self.service.lire_page_web(page.id, **self.source())
        self.assertFalse(read["modifiable"])
        self.assertIn("form", read["raison_non_modifiable"])
        with self.assertRaises(UserError):
            self.service.modifier_page_web(
                page.id, "<p>x</p>", read["sha256"], "Motif", **self.source()
            )
        self.admin.group_ids = [(3, self.env.ref("website.group_website_designer").id)]
        if not self.admin.has_group("website.group_website_designer"):
            with self.assertRaises(AccessError):
                self.service.modifier_page_web(
                    self.page.id, "<p>x</p>", self.read_page()["sha256"], "Motif", **self.source()
                )

    def test_snippet_options_are_kept_but_field_bindings_removed(self):
        clean = sanitize(
            '<section class="s_cover" data-snippet="s_cover" data-name="Couverture" '
            'data-oe-shape-data="{&quot;shape&quot;:&quot;x&quot;}" data-bs-toggle="collapse">'
            '<span data-oe-model="res.partner" data-oe-id="1" data-oe-field="name">Nom</span></section>'
        )
        for kept in ('data-snippet="s_cover"', "data-oe-shape-data", "data-bs-toggle", "data-name"):
            self.assertIn(kept, clean)
        for removed in ("data-oe-model", "data-oe-id", "data-oe-field"):
            self.assertNotIn(removed, clean)

    def test_block_catalogue_serves_editor_ready_static_blocks(self):
        keys, offset = set(), 0
        while offset is not None:
            listing = self.service.lister_blocs_web(offset=offset, **self.source())
            keys |= {b["key"] for b in listing["blocs"]}
            offset = listing["next_offset"]
        self.assertEqual(len(keys), listing["total"])
        self.assertIn("website.s_text_block", keys)
        self.assertFalse(any("_item" in k or "form" in k for k in keys))
        block = self.service.lire_bloc_web("website.s_text_block", **self.source())
        self.assertIn('data-snippet="s_text_block"', block["html"])
        self.assertIn("s_text_block", block["html"])
        with self.assertRaises(UserError):
            self.service.lire_bloc_web("website.s_website_form", **self.source())
        current = self.read_page()
        result = self.service.modifier_page_web(
            self.page.id,
            current["html"] + block["html"],
            current["sha256"],
            "Ajout d'un bloc texte",
            **self.source(),
        )
        self.assertIn('data-snippet="s_text_block"', self.read_page()["html"])
        self.assertTrue(result["audit_id"])

    def test_theme_is_loaded_once_on_a_website_without_theme(self):
        theme = self.env["ir.module.module"].create(
            {"name": "theme_n1_test", "state": "installed", "shortdesc": "Thème de test N1"}
        )
        self.env["ir.module.module"].create({"name": "theme_n1_autre", "state": "installed"})
        self.env["ir.module.module"].create({"name": "theme_n1_absent", "state": "uninstalled"})
        website = self.env["website"].create({"name": "Site N1", "domain": "https://n1.example"})
        result = self.service.appliquer_theme_web(
            website.id, "theme_n1_test", "Thème du nouveau site", **self.source()
        )
        self.assertTrue(result["ok"])
        self.assertEqual(website.theme_id, theme)
        self.assertEqual(result["apres"], {"theme_id": "theme_n1_test"})
        audit = self.env["hermes.n1.change"].browse(result["audit_id"])
        self.assertEqual((audit.target_model, audit.target_id), ("website", website.id))
        self.assertIn("theme_n1_test", str(audit.chatter_message_id.body))
        replay = self.service.appliquer_theme_web(
            website.id, "theme_n1_test", "Thème du nouveau site", **self.source()
        )
        self.assertTrue(replay["deja_applique"])
        # An existing theme is never replaced; only installed theme_* modules are accepted.
        with self.assertRaises(UserError):
            self.service.appliquer_theme_web(
                website.id, "theme_n1_autre", "Autre thème", **self.source()
            )
        self.assertEqual(website.theme_id, theme)
        other = self.env["website"].create({"name": "Site N1 bis"})
        for name in ("theme_n1_absent", "website", "base", None):
            with self.subTest(theme=name), self.assertRaises(UserError):
                self.service.appliquer_theme_web(other.id, name, "Motif", **self.source())
        self.assertFalse(other.theme_id)
        self.admin.group_ids = [(3, self.env.ref("website.group_website_designer").id)]
        if not self.admin.has_group("website.group_website_designer"):
            with self.assertRaises(AccessError):
                self.service.appliquer_theme_web(
                    other.id, "theme_n1_test", "Motif", **self.source()
                )
