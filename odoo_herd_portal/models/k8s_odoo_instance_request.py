import logging
import re
import secrets
import xmlrpc.client
from datetime import timedelta

from kubernetes import client
from markupsafe import Markup
from markupsafe import escape

from odoo import _
from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import AccessError
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

from .k8s_odoo_promotion import herd_is_agent

_logger = logging.getLogger(__name__)

# A DNS label short enough for "<name>-staging" (and the database names
# derived from it) to stay valid: 3 to 30 characters.
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,28}[a-z0-9]$")
NAMESPACE_RE = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
HOST_SUFFIX_RE = re.compile(r"^([a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
RESERVED_NAMES = {
    "admin",
    "api",
    "app",
    "apps",
    "auth",
    "demo",
    "git",
    "herd",
    "imap",
    "login",
    "mail",
    "maison",
    "odoo",
    "office",
    "portal",
    "smtp",
    "sso",
    "staging",
    "test",
    "vault",
    "www",
}
# Unreachable host the production gets until its admin account is secured:
# ".invalid" never resolves (RFC 2606).
PENDING_HOST_SUFFIX = "herd-pending.invalid"
OPEN_STATES = ("requested", "creating", "cloning")
FAILED_PHASES = ("InitFailed", "Error")
STEP_TIMEOUT = timedelta(hours=3)
# Account created by "odoo -i base" (OdooInitJob of a fresh database).
FRESH_LOGIN = FRESH_PASSWORD = "admin"


class K8sOdooInstanceRequest(models.Model):
    _name = "k8s.odoo.instance.request"
    _description = "Request for a new Odoo database"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    partner_id = fields.Many2one(
        "res.partner",
        string="Client",
        required=True,
        readonly=True,
        index=True,
        help="Commercial entity of the requester: it becomes the client of the production.",
    )
    requested_by_id = fields.Many2one(
        "res.users", required=True, readonly=True, default=lambda self: self.env.user
    )
    template_id = fields.Many2one(
        "k8s.odoo.instance.template",
        string="Offer",
        required=True,
        readonly=True,
        ondelete="restrict",
    )
    instance_name = fields.Char(string="Instance Name", required=True, readonly=True)
    host = fields.Char(compute="_compute_hosts", store=True)
    staging_host = fields.Char(compute="_compute_hosts", store=True)
    state = fields.Selection(
        [
            ("requested", "Awaiting approval"),
            ("creating", "Creating the production"),
            ("cloning", "Creating the staging"),
            ("done", "Ready"),
            ("refused", "Refused"),
            ("cancelled", "Cancelled"),
            ("failed", "Failed"),
        ],
        default="requested",
        required=True,
        readonly=True,
        tracking=True,
    )
    approved_by_id = fields.Many2one("res.users", readonly=True, tracking=True)
    approved_at = fields.Datetime(readonly=True)
    production_id = fields.Many2one("k8s.odoo.instance", readonly=True, ondelete="set null")
    staging_id = fields.Many2one("k8s.odoo.instance", readonly=True, ondelete="set null")
    step_started_at = fields.Datetime(readonly=True)
    message = fields.Text(readonly=True)

    @api.depends("instance_name", "template_id.herd_host_suffix")
    def _compute_hosts(self):
        for req in self:
            suffix = req.template_id.herd_host_suffix
            if req.instance_name and suffix:
                req.host = f"{req.instance_name}.{suffix}"
                req.staging_host = f"{req.instance_name}-staging.{suffix}"
            else:
                req.host = req.staging_host = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].sudo().next_by_code("k8s.odoo.instance.request")
                    or "New"
                )
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------
    @api.model
    def _herd_clean_name(self, name):
        name = (name or "").strip().lower()
        if not NAME_RE.match(name) or "--" in name:
            raise ValidationError(
                _(
                    "The name must be 3 to 30 characters: lowercase letters, digits and "
                    "single hyphens, starting with a letter."
                )
            )
        if name in RESERVED_NAMES or name.endswith("-staging"):
            raise ValidationError(_("The name %s is reserved, choose another one.", name))
        return name

    @api.model
    def _herd_check_available(self, name, suffix, exclude_id=None):
        """The name, its hosts and its database must be free everywhere herd
        knows about, and in the open requests."""
        Instance = self.env["k8s.odoo.instance"].sudo()
        hosts = {f"{name}.{suffix}", f"{name}-staging.{suffix}"}
        taken = Instance.search([("name", "in", [name, f"{name}-staging"])], limit=1)
        if not taken:
            for instance in Instance.search([]):
                # odoo_herd joins them with ", "
                if hosts & set(re.split(r"[,\s]+", instance.current_ingress_hosts or "")):
                    taken = instance
                    break
        other = self.sudo().search(
            [
                ("id", "!=", exclude_id or 0),
                ("instance_name", "=", name),
                ("state", "in", OPEN_STATES + ("done",)),
            ],
            limit=1,
        )
        if taken or other:
            raise ValidationError(_("The name %s is already taken.", name))

    @api.model
    def _herd_offers(self):
        return (
            self.env["k8s.odoo.instance.template"]
            .sudo()
            .search([("herd_portal_published", "=", True), ("active", "=", True)])
        )

    @api.model
    def _herd_client_has_database(self, partner):
        return bool(
            self.env["k8s.odoo.instance"]
            .sudo()
            .search_count(
                [("environment", "=", "production"), ("herd_partner_id", "child_of", partner.id)],
                limit=1,
            )
        )

    @api.model
    def _herd_open_request(self, partner):
        return self.sudo().search(
            [("partner_id", "=", partner.id), ("state", "in", OPEN_STATES)], limit=1
        )

    @api.model
    def _herd_can_request(self, user):
        """The portal offers a new database to humans whose client has none
        yet, nor a request in progress."""
        if user._is_public() or herd_is_agent(user) or not self._herd_offers():
            return False
        partner = user.partner_id.commercial_partner_id
        return not self._herd_client_has_database(partner) and not self._herd_open_request(partner)

    def _herd_check_manager(self):
        user = self.env.user
        if not user.has_group("odoo_herd.group_k8s_manager") or herd_is_agent(user):
            raise AccessError(_("Only a human cluster manager can approve or refuse."))

    # ------------------------------------------------------------------
    # Portal façade (public, explicitly checked)
    # ------------------------------------------------------------------
    @api.model
    def herd_request_database(self, template_id, instance_name):
        user = self.env.user
        if user._is_public() or herd_is_agent(user):
            raise AccessError(_("Only a client's human user can request a database."))
        if not user.email:
            raise UserError(_("Add an e-mail address to your account first: it is your login."))
        partner = user.partner_id.commercial_partner_id
        if self._herd_client_has_database(partner):
            raise UserError(_("%s already has an Odoo database.", partner.display_name))
        if self._herd_open_request(partner):
            raise UserError(_("A request is already in progress for %s.", partner.display_name))
        template = self._herd_offers().filtered(lambda t: t.id == int(template_id or 0))
        if not template:
            raise UserError(_("Choose one of the offers."))
        name = self._herd_clean_name(instance_name)
        self._herd_check_available(name, template.herd_host_suffix)
        req = self.sudo().create(
            {
                "partner_id": partner.id,
                "requested_by_id": user.id,
                "template_id": template.id,
                "instance_name": name,
            }
        )
        managers = (
            self.env.ref("odoo_herd.group_k8s_manager")
            .sudo()
            .all_user_ids.filtered(lambda u: not u.share and not herd_is_agent(u))
        )
        req.message_post(
            body=_(
                "%(user)s (%(client)s) requests the database %(host)s, offer %(offer)s: "
                "awaiting the approval of a cluster manager.",
                user=user.display_name,
                client=partner.display_name,
                host=req.host,
                offer=template.name,
            ),
            partner_ids=managers.partner_id.ids,
        )
        return req.id

    @api.model
    def herd_cancel_database_request(self, request_id):
        req = self.sudo().browse(int(request_id)).exists()
        user = self.env.user
        mine = req and req.partner_id == user.partner_id.commercial_partner_id
        if not req or not (mine or user.has_group("odoo_herd.group_k8s_manager")):
            raise AccessError(_("Unknown request."))
        if req.state != "requested":
            raise UserError(_("Only a request awaiting approval can be cancelled."))
        req.write({"state": "cancelled"})
        req.message_post(body=_("Cancelled by %s.", user.display_name))
        return True

    # ------------------------------------------------------------------
    # Backend buttons (a human cluster manager)
    # ------------------------------------------------------------------
    def action_herd_approve(self):
        self._herd_check_manager()
        for req in self:
            if req.state != "requested":
                raise UserError(_("%s is not awaiting approval.", req.name))
            req._herd_check_available(
                req.instance_name, req.template_id.herd_host_suffix, exclude_id=req.id
            )
            req.sudo().write({"approved_by_id": self.env.uid, "approved_at": fields.Datetime.now()})
            req.message_post(body=_("Approved by %s.", self.env.user.display_name))
            req.sudo()._herd_create_production()
        return True

    def action_herd_refuse(self):
        self._herd_check_manager()
        for req in self:
            if req.state != "requested":
                raise UserError(_("%s is not awaiting approval.", req.name))
            req.sudo()._herd_set_step("refused")
            req.message_post(
                body=_("Refused by %s.", self.env.user.display_name),
                partner_ids=req.requested_by_id.partner_id.ids,
            )
        return True

    # ------------------------------------------------------------------
    # Provisioning steps (sudo)
    # ------------------------------------------------------------------
    def _herd_set_step(self, state, **vals):
        self.write(dict(vals, state=state, step_started_at=fields.Datetime.now()))

    def _herd_fail(self, message):
        for req in self:
            req._herd_set_step("failed", message=message)
            req.message_post(body=_("Failed: %s", message))

    def _herd_database_name(self, staging=False):
        name = self.instance_name.replace("-", "_")
        return f"{name}_staging" if staging else name

    def _herd_create_instance(self, staging=False):
        """Create the OdooInstance with the create wizard of odoo_herd, then
        return its synced record."""
        self.ensure_one()
        template = self.template_id
        name = f"{self.instance_name}-staging" if staging else self.instance_name
        values = template.get_template_values()
        values.update(
            {
                "cluster_id": template.herd_cluster_id.id,
                "namespace": template.herd_namespace,
                "template_id": template.id,
                "name": name,
                # Operator master password, never shown: list_db is off anyway.
                "admin_password": secrets.token_urlsafe(24),
                "install_demo_data": False,
            }
        )
        if staging:
            values.update(
                {
                    "environment": "staging",
                    "initialization_mode": "clone_prod",
                    "production_instance_id": self.production_id.id,
                    "ingress_hosts": self.staging_host,
                }
            )
        else:
            values.update(
                {
                    "environment": "production",
                    "initialization_mode": "fresh",
                    # Not reachable until the admin account is secured.
                    "ingress_hosts": f"{name}.{PENDING_HOST_SUFFIX}",
                }
            )
        wizard = (
            self.env["k8s.create.instance.wizard"]
            .with_context(herd_database_name=self._herd_database_name(staging))
            .create(values)
        )
        wizard.action_create_instance()
        instance = self.env["k8s.odoo.instance"].search(
            [
                ("cluster_id", "=", template.herd_cluster_id.id),
                ("namespace", "=", template.herd_namespace),
                ("name", "=", name),
            ],
            limit=1,
        )
        if not instance:
            raise UserError(_("%s was created but is not synced yet.", name))
        return instance

    def _herd_create_production(self):
        self.ensure_one()
        try:
            prod = self._herd_create_instance()
            prod.write(
                {
                    "herd_partner_id": self.partner_id.id,
                    "herd_approver_ids": [(6, 0, self.requested_by_id.ids)],
                }
            )
        except Exception as e:
            _logger.exception("Creation of %s failed", self.instance_name)
            self._herd_fail(_("The production could not be created: %s", e))
            return
        self._herd_set_step("creating", production_id=prod.id)

    def _herd_rpc(self, instance, service, method, *args):
        """XML-RPC call to an instance through the API server's service proxy:
        it reaches a database that has no public host yet."""
        api_client = instance.cluster_id._get_k8s_client()
        path = (
            f"/api/v1/namespaces/{instance.namespace}/services/"
            f"{instance.name}:8069/proxy/xmlrpc/2/{service}"
        )
        data = api_client.call_api(
            path,
            "POST",
            header_params={"Content-Type": "text/xml", "Accept": "text/xml"},
            body=xmlrpc.client.dumps(args, method, allow_none=True),
            auth_settings=["BearerToken"],
            _preload_content=False,
            _return_http_data_only=True,
            _request_timeout=60,
        ).data
        (result,), _method = xmlrpc.client.loads(data)
        return result

    def _herd_secure_admin(self, password):
        """Replace the admin/admin account of the fresh database by the
        requester's login with a random password."""
        self.ensure_one()
        prod, db = self.production_id, self._herd_database_name()
        uid = self._herd_rpc(prod, "common", "authenticate", db, FRESH_LOGIN, FRESH_PASSWORD, {})
        if not uid:
            raise UserError(
                _("The fresh database refused admin/admin: it was changed outside herd.")
            )
        user, partner = self.requested_by_id, self.partner_id

        def call(model, method, *args, **kw):
            return self._herd_rpc(
                prod, "object", "execute_kw", db, uid, FRESH_PASSWORD, model, method, list(args), kw
            )

        call("res.company", "write", [1], {"name": partner.name})
        call(
            "res.users",
            "write",
            [uid],
            {
                "name": user.name,
                "login": user.email,
                "email": user.email,
                "tz": user.tz or "UTC",
                # Last: the session password changes with it.
                "password": password,
            },
        )

    def _herd_patch_hosts(self, instance, host):
        custom_api = client.CustomObjectsApi(instance.cluster_id._get_k8s_client())
        custom_api.patch_namespaced_custom_object(
            group="bemade.org",
            version="v1alpha1",
            namespace=instance.namespace,
            plural="odooinstances",
            name=instance.name,
            body={"spec": {"ingress": {"hosts": [host]}}},
        )

    def _herd_send_access(self, password):
        """The only place the password exists: an e-mail deleted once sent,
        never posted in the chatter."""
        self.ensure_one()
        user = self.requested_by_id
        url = f"https://{self.host}"
        body = Markup(
            "<p>{hello}</p><p>{ready}</p><ul><li>{url_label} <a href='{url}'>{url}</a></li>"
            "<li>{login_label} <code>{login}</code></li>"
            "<li>{password_label} <code>{password}</code></li></ul><p>{change}</p>"
        ).format(
            hello=_("Hello %s,", user.name),
            ready=_("Your Odoo database %s is ready.", self.instance_name),
            url_label=_("Address:"),
            url=url,
            login_label=_("Login:"),
            login=user.email,
            password_label=_("Temporary password:"),
            password=password,
            change=_(
                "Change this password at your first login (your name, top right, then "
                "Preferences / Security). A staging copy will follow at %s.",
                self.staging_host,
            ),
        )
        self.env["mail.mail"].sudo().create(
            {
                "subject": _("Your Odoo database %s is ready", self.instance_name),
                "email_to": user.email_formatted,
                "body_html": body,
                "auto_delete": True,
            }
        )
        self.env.ref("mail.ir_cron_mail_scheduler_action").sudo()._trigger()

    def _herd_commit(self):
        """Commit now (the cron's progress commit, a plain commit elsewhere)."""
        self.env["ir.cron"]._commit_progress()

    def _herd_publish_production(self):
        self.ensure_one()
        password = secrets.token_urlsafe(12)
        try:
            self._herd_secure_admin(password)
        except Exception as e:
            _logger.exception("Securing %s failed", self.instance_name)
            self._herd_fail(
                _(
                    "The production is created but could not be secured; it stays "
                    "unreachable from outside: %s",
                    e,
                )
            )
            return
        # The new password now only exists here: queue it and commit before
        # anything else (host patch, staging sync) can roll the e-mail back.
        self._herd_send_access(password)
        self._herd_set_step("cloning")
        self.message_post(
            body=_(
                "Production secured; access sent to %(email)s for %(host)s.",
                email=self.requested_by_id.email,
                host=self.host,
            )
        )
        self._herd_commit()
        self._herd_finish_publication()

    def _herd_finish_publication(self):
        """Public host, then the staging: both idempotent, so a run cut short
        after the commit above resumes here."""
        self.ensure_one()
        try:
            self._herd_patch_hosts(self.production_id, self.host)
        except Exception:
            _logger.exception("Host of %s failed, retrying later", self.instance_name)
            return
        try:
            staging = self._herd_create_instance(staging=True)
            staging.write({"herd_agent_allowed": False})
        except Exception as e:
            _logger.exception("Staging of %s failed", self.instance_name)
            self._herd_fail(_("The production is ready, but the staging failed: %s", e))
            return
        self.write({"staging_id": staging.id})

    def _herd_advance(self):
        for req in self.sudo():
            if req.state == "creating":
                phase = req.production_id.phase
                if not req.production_id:
                    req._herd_fail(_("The production disappeared from the cluster."))
                elif phase in FAILED_PHASES:
                    req._herd_fail(_("The production failed to start (%s).", phase))
                elif phase == "Running":
                    req._herd_publish_production()
            elif req.state == "cloning" and not req.staging_id:
                req._herd_finish_publication()
            elif req.state == "cloning":
                phase = req.staging_id.phase
                if phase in FAILED_PHASES:
                    req._herd_fail(
                        _("The production is ready, but the staging failed (%s).", phase)
                    )
                elif phase == "Running":
                    req._herd_set_step("done", message=_("Production and staging are ready."))
                    req.message_post(
                        body=Markup("{} <a href='https://{}'>{}</a>").format(
                            _("Ready:"), req.host, escape(req.host)
                        ),
                        partner_ids=req.requested_by_id.partner_id.ids,
                    )

    @api.model
    def _cron_herd_requests(self):
        running = self.sudo().search([("state", "in", ("creating", "cloning"))])
        now = fields.Datetime.now()
        stuck = running.filtered(lambda r: r.step_started_at < now - STEP_TIMEOUT)
        stuck._herd_fail(_("No news from the cluster for 3 hours."))
        (running - stuck)._herd_advance()
