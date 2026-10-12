from datetime import datetime
from urllib.parse import urlencode

import pytz
from werkzeug.exceptions import NotFound

from odoo import _
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.exceptions import AccessError
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.http import route

from ..models.k8s_odoo_promotion import herd_is_agent


def _short_image(image):
    if not image:
        return "-"
    repo, _sep, digest = image.partition("@sha256:")
    return f"{repo.rsplit('/', 1)[-1]}@{digest[:12]}" if digest else image


class HerdPortal(CustomerPortal):
    # ------------------------------------------------------------------
    # Helpers: every value handed to the templates is whitelisted here;
    # portal users have no access right on the k8s models.
    # ------------------------------------------------------------------
    def _herd_domain(self):
        user = request.env.user
        domain = [("environment", "=", "production")]
        if user.has_group("odoo_herd.group_k8s_manager"):
            return domain
        partner = user.partner_id.commercial_partner_id
        return domain + [
            "|",
            ("herd_approver_ids", "in", user.id),
            ("herd_partner_id", "child_of", partner.id),
        ]

    def _herd_production(self, production_id):
        prod = request.env["k8s.odoo.instance"].sudo().browse(production_id).exists()
        if not prod or not prod._herd_portal_allowed(request.env.user):
            raise NotFound()
        return prod

    def _herd_instance_values(self, instance):
        return {
            "id": instance.id,
            "name": instance.name,
            "namespace": instance.namespace,
            "url": instance.url,
            "phase": dict(instance._fields["phase"]._description_selection(instance.env)).get(
                instance.phase, "-"
            ),
            # Image the cluster runs; the stored field can lag behind.
            "image": instance.current_image or instance.image,
            "image_short": _short_image(instance.current_image or instance.image),
        }

    def _herd_promotion_values(self, promotion):
        state = dict(promotion._fields["state"]._description_selection(promotion.env))
        return {
            "id": promotion.id,
            "name": promotion.name,
            "state": promotion.state,
            "state_label": state.get(promotion.state),
            "staging": promotion.staging_id.name,
            "image_short": _short_image(promotion.image),
            "staging_changed": (promotion.staging_id.current_image or promotion.staging_id.image)
            != promotion.image,
            "modules": promotion.modules or "",
            "modules_install": promotion.modules_install or "",
            "scheduled_at": promotion.scheduled_at,
            "requested_by": promotion.requested_by_id.name,
            "requested_by_agent": promotion.requested_by_agent,
            "confirmed_by": promotion.confirmed_by_id.name,
            "message": promotion.message,
            "create_date": promotion.create_date,
        }

    def _herd_redirect(self, prod, message=None, error=None):
        url = f"/my/odoo/{prod.id}"
        params = []
        if message:
            params.append(("herd_message", message))
        if error:
            params.append(("herd_error", error))
        if params:
            url += "?" + urlencode(params)
        return request.redirect(url)

    def _herd_parse_local_datetime(self, value):
        """datetime-local form value, in the user's time zone, to UTC."""
        if not value:
            return None
        try:
            local = datetime.strptime(value[:16], "%Y-%m-%dT%H:%M")
        except ValueError as e:
            raise UserError(_("Invalid date: %s", value)) from e
        tz = pytz.timezone(request.env.user.tz or "UTC")
        return tz.localize(local).astimezone(pytz.utc).replace(tzinfo=None)

    def _prepare_portal_counter_values(self, counter):
        if counter == "herd_instance_count":
            return "k8s.odoo.instance", self._herd_domain(), "sudo"
        return super()._prepare_portal_counter_values(counter)

    @route()
    def counters(self, counters, **kw):
        res = super().counters(counters, **kw)
        # The card is always displayed (portal_home_counters patch) when the
        # counter is returned: drop it for users with nothing to see nor ask.
        if res.get("herd_instance_count") == 0:
            Request = request.env["k8s.odoo.instance.request"]
            user = request.env.user
            partner = user.partner_id.commercial_partner_id
            if not Request._herd_can_request(user) and not Request._herd_open_request(partner):
                res.pop("herd_instance_count")
        return res

    def _herd_request_values(self, req):
        state = dict(req._fields["state"]._description_selection(req.env))
        return {
            "id": req.id,
            "name": req.name,
            "state": req.state,
            "state_label": state.get(req.state),
            "instance_name": req.instance_name,
            "host": req.host,
            "offer": req.template_id.name,
            "requested_by": req.requested_by_id.name,
            "create_date": req.create_date,
            "message": req.message if req.state in ("refused", "failed") else False,
        }

    def _herd_requests(self):
        partner = request.env.user.partner_id.commercial_partner_id
        reqs = (
            request.env["k8s.odoo.instance.request"]
            .sudo()
            .search(
                [
                    ("partner_id", "=", partner.id),
                    ("state", "not in", ("done", "cancelled")),
                ],
                limit=5,
            )
        )
        return [self._herd_request_values(r) for r in reqs]

    def _herd_list_redirect(self, message=None, error=None):
        params = []
        if message:
            params.append(("herd_message", message))
        if error:
            params.append(("herd_error", error))
        return request.redirect("/my/odoo" + ("?" + urlencode(params) if params else ""))

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------
    @route("/my/odoo", type="http", auth="user", website=True)
    def herd_instances(self, herd_message=None, herd_error=None, **kw):
        prods = request.env["k8s.odoo.instance"].sudo().search(self._herd_domain())
        values = self._prepare_portal_layout_values()
        values.update(
            {
                "page_name": "herd_instances",
                "herd_message": herd_message,
                "herd_error": herd_error,
                "herd_can_request": request.env["k8s.odoo.instance.request"]._herd_can_request(
                    request.env.user
                ),
                "herd_requests": self._herd_requests(),
                "herd_productions": [
                    dict(
                        self._herd_instance_values(p),
                        stagings=len(p.herd_staging_ids),
                        pending=len(
                            p.herd_promotion_ids.filtered(lambda r: r.state == "requested")
                        ),
                    )
                    for p in prods
                ],
            }
        )
        return request.render("odoo_herd_portal.portal_my_odoo_instances", values)

    @route("/my/odoo/new", type="http", auth="user", website=True)
    def herd_new_database(self, herd_error=None, instance_name=None, template_id=None, **kw):
        Request = request.env["k8s.odoo.instance.request"]
        if not Request._herd_can_request(request.env.user):
            return request.redirect("/my/odoo")
        values = self._prepare_portal_layout_values()
        values.update(
            {
                "page_name": "herd_new_database",
                "herd_error": herd_error,
                "herd_offers": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "description": t.herd_portal_description or "",
                        "host_suffix": t.herd_host_suffix,
                    }
                    for t in Request._herd_offers()
                ],
                "herd_instance_name": instance_name or "",
                "herd_template_id": int(template_id or 0),
            }
        )
        return request.render("odoo_herd_portal.portal_my_odoo_new", values)

    @route(
        "/my/odoo/new/submit",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def herd_new_database_submit(self, template_id=None, instance_name=None, **kw):
        try:
            request.env["k8s.odoo.instance.request"].herd_request_database(
                template_id, instance_name
            )
        except (AccessError, UserError, ValidationError) as e:
            params = urlencode(
                {
                    "herd_error": str(e),
                    "instance_name": instance_name or "",
                    "template_id": template_id or "",
                }
            )
            return request.redirect(f"/my/odoo/new?{params}")
        return self._herd_list_redirect(
            message=_("Request sent: we create your database once it is approved.")
        )

    @route(
        "/my/odoo/request/<int:request_id>/cancel",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def herd_cancel_database_request(self, request_id, **kw):
        try:
            request.env["k8s.odoo.instance.request"].herd_cancel_database_request(request_id)
        except (AccessError, UserError, ValidationError) as e:
            return self._herd_list_redirect(error=str(e))
        return self._herd_list_redirect(message=_("Request cancelled."))

    @route("/my/odoo/<int:production_id>", type="http", auth="user", website=True)
    def herd_instance(self, production_id, herd_message=None, herd_error=None, **kw):
        prod = self._herd_production(production_id)
        user = request.env.user
        values = self._prepare_portal_layout_values()
        values.update(
            {
                "page_name": "herd_instance",
                "herd_prod": self._herd_instance_values(prod),
                "herd_stagings": [self._herd_instance_values(s) for s in prod.herd_staging_ids],
                "herd_promotions": [
                    self._herd_promotion_values(p) for p in prod.herd_promotion_ids[:20]
                ],
                "herd_is_approver": user in prod.herd_approver_ids and not herd_is_agent(user),
                "herd_confirm_method": request.env["k8s.odoo.promotion"]
                .sudo()
                .new({"production_id": prod.id})
                ._herd_confirm_method(user),
                "herd_message": herd_message,
                "herd_error": herd_error,
            }
        )
        return request.render("odoo_herd_portal.portal_my_odoo_instance", values)

    # ------------------------------------------------------------------
    # Actions (POST + CSRF only)
    # ------------------------------------------------------------------
    def _herd_staging(self, prod, staging_id):
        staging = prod.herd_staging_ids.filtered(lambda s: s.id == int(staging_id or 0))
        if not staging:
            raise NotFound()
        return staging

    def _herd_promotion(self, prod, promotion_id):
        promotion = prod.herd_promotion_ids.filtered(lambda p: p.id == int(promotion_id))
        if not promotion:
            raise NotFound()
        return promotion

    @route(
        "/my/odoo/<int:production_id>/resync",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def herd_resync(self, production_id, staging_id=None, **kw):
        prod = self._herd_production(production_id)
        staging = self._herd_staging(prod, staging_id)
        try:
            request.env["k8s.odoo.promotion"].herd_resync_staging(staging.id)
        except (AccessError, UserError, ValidationError) as e:
            return self._herd_redirect(prod, error=str(e))
        return self._herd_redirect(
            prod, message=_("Resync of %s started: it takes a few minutes.", staging.name)
        )

    @route(
        "/my/odoo/<int:production_id>/promote",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def herd_promote(
        self,
        production_id,
        staging_id=None,
        modules=None,
        scheduled_at=None,
        modules_install=None,
        **kw,
    ):
        prod = self._herd_production(production_id)
        staging = self._herd_staging(prod, staging_id)
        try:
            when = self._herd_parse_local_datetime(scheduled_at)
            request.env["k8s.odoo.promotion"].herd_request_promotion(
                staging.id,
                modules=modules or None,
                scheduled_at=when,
                modules_install=modules_install or None,
            )
        except (AccessError, UserError, ValidationError) as e:
            return self._herd_redirect(prod, error=str(e))
        return self._herd_redirect(
            prod, message=_("Promotion requested. An approver must now confirm it.")
        )

    @route(
        "/my/odoo/<int:production_id>/promotion/<int:promotion_id>/send-code",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def herd_send_code(self, production_id, promotion_id, **kw):
        prod = self._herd_production(production_id)
        promotion = self._herd_promotion(prod, promotion_id)
        try:
            promotion._herd_send_code(request.env.user)
        except (AccessError, UserError, ValidationError) as e:
            return self._herd_redirect(prod, error=str(e))
        return self._herd_redirect(
            prod, message=_("A code was sent to %s.", request.env.user.email)
        )

    @route(
        "/my/odoo/<int:production_id>/promotion/<int:promotion_id>/confirm",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def herd_confirm(self, production_id, promotion_id, code=None, **kw):
        prod = self._herd_production(production_id)
        promotion = self._herd_promotion(prod, promotion_id)
        try:
            confirmed = promotion._herd_confirm(request.env.user, code)
        except (AccessError, UserError, ValidationError) as e:
            return self._herd_redirect(prod, error=str(e))
        if not confirmed:
            return self._herd_redirect(prod, error=_("Wrong code."))
        return self._herd_redirect(prod, message=_("Promotion %s confirmed.", promotion.name))

    @route(
        "/my/odoo/<int:production_id>/promotion/<int:promotion_id>/cancel",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def herd_cancel(self, production_id, promotion_id, **kw):
        prod = self._herd_production(production_id)
        promotion = self._herd_promotion(prod, promotion_id)
        try:
            request.env["k8s.odoo.promotion"].herd_cancel(promotion.id)
        except (AccessError, UserError, ValidationError) as e:
            return self._herd_redirect(prod, error=str(e))
        return self._herd_redirect(prod, message=_("Promotion %s cancelled.", promotion.name))
