"""Website page body for Hermes N1: the editable #wrap section, never the QWeb view.

A page's content lives in the ``arch`` of its ``ir.ui.view`` (QWeb, executed server side),
which N1's generic facade excludes as a technical model. This facade only replaces the
``<div id="wrap">`` section, through the website editor's own ``ir.ui.view.save`` with the
requesting administrator's rights, after sanitizing the HTML to plain content: no QWeb, no
script, no event handler, no editor metadata (``data-oe-*`` would let the editor write other
records' fields). A section that already contains QWeb is left to the web editor.
"""

import hashlib
import json

from lxml import etree
from lxml import html as lxml_html
from markupsafe import Markup

from odoo import api
from odoo import models
from odoo.addons.hermes_n1_audit.agent_html import agent_html
from odoo.addons.hermes_n1_audit.agent_html import values_table
from odoo.exceptions import AccessError
from odoo.exceptions import UserError

WRAP_XPATH = "//div[@id='wrap']"
MAX_HTML = 200_000
DROP_TAGS = {
    "script",
    "style",
    "iframe",
    "frame",
    "frameset",
    "object",
    "embed",
    "applet",
    "form",
    "input",
    "textarea",
    "select",
    "link",
    "meta",
    "base",
    "svg",
    "math",
    "template",
    "noscript",
}
URL_ATTRS = {"href", "src", "action", "formaction", "xlink:href", "poster", "background", "srcset"}
# Editor metadata that binds an element to another record's field: save() would write it.
# Other data-oe-* (shape data, version) are snippet options and are kept.
FIELD_BINDING = (
    "data-oe-model",
    "data-oe-id",
    "data-oe-field",
    "data-oe-xpath",
    "data-oe-expression",
    "data-oe-type",
    "data-oe-source-id",
    "data-oe-many2one",
    "data-oe-contact-options",
    "data-oe-translation",
    "data-oe-nodeid",
)
# Snippets that are parts of others, popups or dynamic (server data, forms, maps, scripts).
NOT_A_BLOCK = (
    "_item",
    "_template",
    "popup",
    "dynamic",
    "form",
    "map",
    "blog",
    "product",
    "event",
    "newsletter",
    "searchbar",
    "chart",
    "countdown",
    "social_media",
    "embed",
    "instagram",
)


def _digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _inner(element):
    return (element.text or "") + "".join(
        etree.tostring(child, encoding="unicode", method="html") for child in element
    )


def _blocked(element):
    """Why N1 must not rewrite this section, or None.

    QWeb is dynamic content; and anything the sanitizer would drop (a contact form, an
    embedded map, a script) would be destroyed by a rewrite. Those stay in the web editor.
    """
    for node in element.iter():
        if not isinstance(node.tag, str) or node is element:
            continue
        if node.tag == "t" or any(str(name).startswith("t-") for name in node.attrib):
            return "parties dynamiques (QWeb)"
        if node.tag.lower() in DROP_TAGS:
            return "élément <%s> (formulaire, intégration ou script)" % node.tag.lower()
    return None


def sanitize(fragment):
    """Plain editable HTML: QWeb, scripts, handlers, editor metadata and unsafe URLs removed."""
    wrapper = lxml_html.fragment_fromstring(fragment, create_parent="div")
    for node in list(wrapper.iter()):
        if not isinstance(node.tag, str):  # comments, processing instructions
            if node.getparent() is not None:
                node.drop_tree()
            continue
        if node is wrapper:
            continue
        tag = node.tag.lower()
        if tag == "t":
            node.drop_tag()
            continue
        if tag in DROP_TAGS:
            node.drop_tree()
            continue
        for name in list(node.attrib):
            value = node.attrib[name].strip().lower().replace("\x00", "")
            lowered = name.lower()
            if (
                lowered.startswith(("t-", "on", *FIELD_BINDING))
                or lowered == "contenteditable"
                or (
                    lowered in URL_ATTRS
                    and value.startswith(("javascript:", "vbscript:", "data:"))
                    and not (
                        lowered == "src" and value.startswith("data:image/") and "svg" not in value
                    )
                )
            ):
                del node.attrib[name]
    return _inner(wrapper)


class HermesN1ChangeWebsite(models.Model):
    _inherit = "hermes.n1.change"

    def _page_wrap(self, page_id, actor):
        if type(page_id) is not int or page_id <= 0:
            raise UserError(self.env._("Identifiant de page positif requis."))
        page = self.env["website.page"].with_user(actor).browse(page_id).exists()
        if not page:
            raise UserError(self.env._("Page absente."))
        page.check_access("read")
        website = page.website_id or self.env["website"].sudo().search([], order="id", limit=1)
        view = page.view_id.with_user(actor).with_context(website_id=website.id)
        arch = etree.fromstring(view.get_combined_arch())
        wrap = arch.xpath(WRAP_XPATH)
        if len(wrap) != 1:
            raise UserError(
                self.env._("Cette page n'a pas de zone #wrap éditable ; passer par l'éditeur web.")
            )
        return page, website, view, wrap[0]

    @api.model
    def lire_page_web(self, page_id, channel_id, message_id, partner_id):
        actor, _source = self._business_actor(channel_id, message_id, partner_id)
        page, website, _view, wrap = self._page_wrap(page_id, actor)
        content = _inner(wrap)
        return {
            "page_id": page.id,
            "url": page.url,
            "name": page.name,
            "website_id": website.id,
            "html": content,
            "sha256": _digest(content),
            "modifiable": not _blocked(wrap),
            "raison_non_modifiable": _blocked(wrap) or False,
        }

    @api.model
    def modifier_page_web(
        self, page_id, html, expected_sha256, reason, channel_id, message_id, partner_id
    ):
        actor, source = self._business_actor(channel_id, message_id, partner_id)
        if not isinstance(html, str) or not html.strip() or len(html) > MAX_HTML:
            raise UserError(self.env._("Contenu HTML requis, %d caractères au plus.", MAX_HTML))
        if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
            raise UserError(self.env._("Empreinte sha256 lue par lire_page_web requise."))
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise UserError(self.env._("Motif obligatoire."))
        if not actor.has_group("website.group_website_designer"):
            raise AccessError(self.env._("Le demandeur n'a pas le droit de modifier le site."))
        clean = sanitize(html)
        key = hashlib.sha256(
            json.dumps(
                [self.env.uid, source.id, "website.page", page_id, _digest(clean), expected_sha256],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        with self.env.cr.savepoint():
            self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", [int(key[:15], 16)])
            previous = self.sudo().search([("request_key", "=", key)], limit=1)
            if previous:
                return previous._result(replayed=True)
            page, _website, view, wrap = self._page_wrap(page_id, actor)
            before = _inner(wrap)
            if _digest(before) != expected_sha256:
                raise UserError(
                    self.env._("Page modifiée depuis la lecture ; relire avant de modifier.")
                )
            blocked = _blocked(wrap)
            if blocked:
                raise UserError(
                    self.env._(
                        "Cette page contient des %s : la modifier dans l'éditeur web.", blocked
                    )
                )
            section = etree.Element("div", dict(wrap.attrib))
            fragment = lxml_html.fragment_fromstring(clean or "", create_parent="div")
            section.text, section[:] = fragment.text, list(fragment)
            view.save(etree.tostring(section, encoding="unicode", method="html"), xpath=WRAP_XPATH)
            self.env.flush_all()
            _page, _website, _view, wrap_after = self._page_wrap(page_id, actor)
            after = _inner(wrap_after)
            audit = (
                self.sudo()
                .with_context(mail_create_nosubscribe=True)
                .create(
                    {
                        "request_key": key,
                        "target_model": "website.page",
                        "target_id": page.id,
                        "requester_id": actor.id,
                        "agent_id": self.env.uid,
                        "source_message_id": source.id,
                        "reason": reason.strip(),
                        "before_values": {
                            "url": page.url,
                            "sha256": _digest(before),
                            "html": before,
                        },
                        "after_values": {"url": page.url, "sha256": _digest(after), "html": after},
                    }
                )
            )
            body = (
                (
                    Markup("<p><strong>Hermes N1 : contenu de la page %s modifié</strong></p>")
                    % page.url
                )
                + Markup('<p class="mb-1"><strong>Motif</strong></p>')
                + agent_html(reason)
                + values_table(
                    {"sha256": _digest(before), "longueur": len(before)},
                    {"sha256": _digest(after), "longueur": len(after)},
                    {"sha256": "Empreinte du contenu", "longueur": "Longueur (caractères)"},
                )
            )
            note = audit.with_context(
                mail_notify_noemail=True, mail_post_autofollow=False
            ).message_post(
                body=body,
                author_id=self.env.user.partner_id.id,
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
            if not note:
                raise UserError(self.env._("Journal obligatoire."))
            models.Model.write(audit, {"chatter_message_id": note.id})
            result = audit._result()
            result.update({"url": page.url, "sha256": _digest(after)})
            return result

    # -- Odoo snippet catalogue -------------------------------------------------------------

    @api.model
    def _block_views(self):
        views = (
            self.env["ir.ui.view"]
            .sudo()
            .search(
                [
                    ("key", "=like", "website.s\\_%"),
                    ("type", "=", "qweb"),
                    ("inherit_id", "=", False),
                ],
                order="key",
            )
        )
        return views.filtered(lambda v: not any(part in v.key for part in NOT_A_BLOCK))

    @api.model
    def lister_blocs_web(self, channel_id, message_id, partner_id, offset=0):
        """Static Odoo website blocks N1 may compose pages with (key and label)."""
        self._business_actor(channel_id, message_id, partner_id)
        if type(offset) is not int or offset < 0:
            raise UserError(self.env._("offset doit être un entier positif ou nul."))
        views = self._block_views()
        page = views[offset : offset + 60]
        return {
            "blocs": [{"key": v.key, "name": v.name} for v in page],
            "total": len(views),
            "next_offset": offset + 60 if offset + 60 < len(views) else None,
        }

    @api.model
    def lire_bloc_web(self, key, channel_id, message_id, partner_id):
        """HTML of a block as the web editor inserts it, rendered by Odoo."""
        self._business_actor(channel_id, message_id, partner_id)
        view = self._block_views().filtered(lambda v: v.key == key)
        if not isinstance(key, str) or not view:
            raise UserError(self.env._("Bloc inconnu ; consulter lister_blocs_web."))
        website = self.env["website"].sudo().search([], order="id", limit=1)
        try:
            rendered = str(
                self.env["ir.qweb"]
                .with_context(website_id=website.id)
                ._render(view.key, {"website": website})
            )
        except Exception:  # noqa: BLE001 - any rendering failure means "not usable here"
            raise UserError(
                self.env._("Ce bloc ne peut pas être préparé ici ; l'insérer depuis l'éditeur web.")
            ) from None
        fragment = lxml_html.fragment_fromstring(rendered.strip(), create_parent="div")
        if _blocked(fragment) or len(fragment) != 1:
            raise UserError(
                self.env._(
                    "Ce bloc contient des éléments dynamiques ; l'insérer depuis l'éditeur web."
                )
            )
        root = fragment[0]
        root.set("data-snippet", view.key.split(".", 1)[1])
        root.set("data-name", view.name or view.key)
        block = etree.tostring(root, encoding="unicode", method="html")
        return {"key": view.key, "name": view.name, "html": sanitize(block)}
