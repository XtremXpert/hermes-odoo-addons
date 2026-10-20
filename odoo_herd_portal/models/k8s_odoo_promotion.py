import hashlib
import hmac
import logging
import re
import secrets
from datetime import timedelta

from markupsafe import Markup
from markupsafe import escape

from odoo import _
from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import AccessDenied
from odoo.exceptions import AccessError
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

DIGEST_RE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
MODULE_RE = re.compile(r"^[a-z0-9_]+$")
CODE_TTL = timedelta(minutes=10)
CODE_RESEND_DELAY = timedelta(seconds=60)
CODE_MAX_ATTEMPTS = 5
STEP_TIMEOUT = timedelta(hours=6)
# Once a promotion leaves "requested", what was confirmed can no longer change.
FROZEN_FIELDS = {
    "production_image",
    "production_id",
    "staging_id",
    "image",
    "modules",
    "modules_install",
    "scheduled_at",
}
RUNNING_STATES = ("backing_up", "deploying", "upgrading")


def herd_is_agent(user):
    """True for automated accounts: staging operators and Hermes agents.

    Based on group membership, never on the context, which any RPC caller
    controls.
    """
    user = user.sudo()
    operator = user.env.ref("odoo_herd_portal.group_staging_operator", raise_if_not_found=False)
    if operator and operator in user.all_group_ids:
        return True
    hermes = user.env["ir.model.data"].search(
        [("model", "=", "res.groups"), ("module", "=like", "hermes\\_%")]
    )
    return bool(set(hermes.mapped("res_id")) & set(user.all_group_ids.ids))


def check_digest(env, image):
    if not image or not DIGEST_RE.match(image):
        raise ValidationError(
            env._(
                "The image must be pinned by digest (…@sha256:<64 hex>), not by tag: %s",
                image or "-",
            )
        )


class K8sOdooPromotion(models.Model):
    _name = "k8s.odoo.promotion"
    _description = "Promotion of a staging image to production"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    production_id = fields.Many2one(
        "k8s.odoo.instance",
        string="Production",
        required=True,
        readonly=True,
        ondelete="restrict",
        index=True,
    )
    staging_id = fields.Many2one(
        "k8s.odoo.instance",
        string="Staging",
        required=True,
        readonly=True,
        ondelete="restrict",
    )
    partner_id = fields.Many2one(related="production_id.herd_partner_id", store=True)
    image = fields.Char(
        required=True,
        readonly=True,
        help="Staging image, pinned by digest when the promotion was requested. "
        "Production receives exactly this image.",
    )
    production_image = fields.Char(
        readonly=True,
        help="Production image when the promotion was requested: if production "
        "has changed since, the promotion is refused instead of rolling it back.",
    )
    previous_image = fields.Char(
        readonly=True, help="Production image before the promotion, for a rollback."
    )
    modules = fields.Char(
        readonly=True,
        help="Comma-separated modules to update once the image is deployed. "
        "Empty: no module update.",
    )
    modules_install = fields.Char(
        string="Modules to install",
        readonly=True,
        help="Comma-separated new modules to install once the image is deployed, "
        "as already tested on the staging. Empty: nothing to install.",
    )
    scheduled_at = fields.Datetime(
        string="Scheduled for",
        readonly=True,
        help="Empty: right after confirmation.",
    )
    state = fields.Selection(
        [
            ("requested", "Awaiting confirmation"),
            ("scheduled", "Scheduled"),
            ("backing_up", "Backing up production"),
            ("deploying", "Deploying"),
            ("upgrading", "Updating modules"),
            ("done", "Done"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        default="requested",
        required=True,
        readonly=True,
        tracking=True,
    )
    requested_by_id = fields.Many2one(
        "res.users", readonly=True, default=lambda self: self.env.user
    )
    requested_by_agent = fields.Boolean(readonly=True)
    confirmed_by_id = fields.Many2one("res.users", readonly=True, tracking=True)
    confirmed_at = fields.Datetime(readonly=True)
    confirm_method = fields.Selection(
        [("totp", "Authenticator app"), ("email", "Code by e-mail")],
        string="Confirmed with",
        readonly=True,
    )
    backup_id = fields.Many2one("k8s.odoo.backup", readonly=True)
    upgrade_id = fields.Many2one("k8s.odoo.upgrade", readonly=True)
    step_started_at = fields.Datetime(readonly=True)
    message = fields.Text(readonly=True)
    # One-time confirmation code: only its keyed hash is stored, unreadable
    # through the ORM.
    code_hash = fields.Char(groups=fields.NO_ACCESS, copy=False)
    code_user_id = fields.Many2one("res.users", groups=fields.NO_ACCESS, copy=False)
    code_expires_at = fields.Datetime(groups=fields.NO_ACCESS, copy=False)
    code_sent_at = fields.Datetime(groups=fields.NO_ACCESS, copy=False)
    code_attempts = fields.Integer(groups=fields.NO_ACCESS, copy=False)

    # ------------------------------------------------------------------
    # Integrity
    # ------------------------------------------------------------------
    @api.constrains("production_id", "staging_id", "image", "modules", "modules_install")
    def _check_pair(self):
        for promotion in self:
            prod, staging = promotion.production_id, promotion.staging_id
            if prod.environment != "production":
                raise ValidationError(_("The target must be a production instance."))
            if staging.environment != "staging":
                raise ValidationError(_("The source must be a staging instance."))
            if staging.production_instance_id != prod:
                raise ValidationError(
                    _(
                        "%(staging)s is not the staging of %(prod)s.",
                        staging=staging.display_name,
                        prod=prod.display_name,
                    )
                )
            check_digest(self.env, promotion.image)
            for module in promotion._module_list() + promotion._module_list("modules_install"):
                if not MODULE_RE.match(module):
                    raise ValidationError(_("Invalid module name: %s", module))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].sudo().next_by_code("k8s.odoo.promotion") or "New"
                )
        return super().create(vals_list)

    def write(self, vals):
        frozen = FROZEN_FIELDS & set(vals)
        if frozen and any(p.state != "requested" for p in self):
            raise UserError(
                _("A confirmed promotion cannot be changed: %s", ", ".join(sorted(frozen)))
            )
        if frozen:
            # What the approver received no longer matches: void the code.
            vals = dict(vals, code_hash=False, code_expires_at=False)
        return super().write(vals)

    def unlink(self):
        if any(p.state not in ("requested", "cancelled") for p in self):
            raise UserError(_("Only unconfirmed promotions can be deleted."))
        return super().unlink()

    def _module_list(self, field="modules"):
        self.ensure_one()
        return [m.strip() for m in (self[field] or "").split(",") if m.strip()]

    # ------------------------------------------------------------------
    # Façade for agents and the portal (public, explicitly checked)
    # ------------------------------------------------------------------
    @api.model
    def herd_request_promotion(
        self, staging_id, modules=None, scheduled_at=None, modules_install=None, replace=False
    ):
        """Ask to move the production to the code of this staging.

        Agents may call it; the promotion then waits for a human approver.
        With ``replace``, the caller's own unconfirmed requests for this staging
        are cancelled: the CI asks again after each delivery, with the full list
        of modules. Requests of other users are never touched.
        """
        staging = self.env["k8s.odoo.instance"].sudo().browse(int(staging_id)).exists()
        self._herd_check_can_request(staging)
        if staging.environment != "staging" or not staging.production_instance_id:
            raise UserError(_("Promotions start from a staging linked to a production."))
        if scheduled_at and fields.Datetime.to_datetime(scheduled_at) <= fields.Datetime.now():
            raise UserError(_("The scheduled time must be in the future."))
        if isinstance(modules, (list, tuple)):
            modules = ",".join(modules)
        if isinstance(modules_install, (list, tuple)):
            modules_install = ",".join(modules_install)
        # Live images, never the stored `image` field: it can be stale.
        image = staging._herd_live_image()
        production_image = staging.production_instance_id._herd_live_image()
        if image == production_image and not modules and not modules_install:
            raise UserError(
                _(
                    "The production already runs this staging's code: "
                    "name the modules to update or to install."
                )
            )
        promotion = self.sudo().create(
            {
                "production_id": staging.production_instance_id.id,
                "staging_id": staging.id,
                "image": image,
                "production_image": production_image,
                "modules": modules or False,
                "modules_install": modules_install or False,
                "scheduled_at": scheduled_at or False,
                "requested_by_id": self.env.uid,
                "requested_by_agent": herd_is_agent(self.env.user),
            }
        )
        promotion.message_post(
            body=_(
                "Promotion requested by %s, awaiting a human approver.", self.env.user.display_name
            )
        )
        if replace:
            previous = self.sudo().search(
                [
                    ("staging_id", "=", staging.id),
                    ("state", "=", "requested"),
                    ("requested_by_id", "=", self.env.uid),
                    ("id", "!=", promotion.id),
                ]
            )
            previous.write({"state": "cancelled", "code_hash": False})
            for old in previous:
                old.message_post(body=_("Replaced by %s.", promotion.name))
        return promotion.id

    @api.model
    def herd_resync_staging(self, staging_id):
        """Replace the staging database and filestore by a neutralized copy
        of its own production. Never targets a production.

        On the production's cluster and namespace the production is cloned;
        a staging of another cluster gets the production's latest S3 backup.

        :returns: id of the k8s.odoo.staging.refresh or k8s.odoo.restore
        """
        staging = self.env["k8s.odoo.instance"].sudo().browse(int(staging_id)).exists()
        self._herd_check_can_operate(staging)
        if staging.environment != "staging" or not staging.production_instance_id:
            raise UserError(_("Only a staging linked to a production can be resynced."))
        refresh = staging._herd_resync_from(staging.production_instance_id, neutralize=True)
        staging.message_post(
            body=_(
                "Resync from %(prod)s requested by %(user)s (%(refresh)s).",
                prod=staging.production_instance_id.display_name,
                user=self.env.user.display_name,
                refresh=refresh.name,
            )
        )
        return refresh.id

    @api.model
    def herd_deploy_staging(self, staging_id, image, modules=None):
        """Deploy an image (pinned by digest) on a staging. Never a production.

        ``modules`` are updated on the staging once the new image is rolled
        out (cron, or the next herd_staging_status call): updating while the
        pods restart would time out on the registry lock (PROMO/0017).
        """
        staging = self.env["k8s.odoo.instance"].sudo().browse(int(staging_id)).exists()
        user = self.env.user
        is_manager = user.has_group("odoo_herd.group_k8s_manager")
        if not (is_manager or (herd_is_agent(user) and staging.herd_agent_allowed)):
            raise AccessError(_("You cannot deploy on this staging."))
        if staging.environment != "staging":
            raise AccessError(_("Only a staging can be deployed this way."))
        check_digest(self.env, image)
        if isinstance(modules, (list, tuple)):
            modules = ",".join(modules)
        names = [m.strip() for m in (modules or "").split(",") if m.strip()]
        for module in names:
            if not MODULE_RE.match(module):
                raise ValidationError(_("Invalid module name: %s", module))
        staging._herd_patch_image(image)
        # Already on the cluster: not an edit waiting for "Sync to Cluster".
        staging._herd_deploy_write(
            {
                "image": image,
                "herd_deploy_image": image,
                "herd_deploy_modules": ",".join(names) or False,
                "herd_deploy_upgrade_id": False,
            }
        )
        staging.message_post(
            body=_(
                "Image %(image)s deployed by %(user)s. Modules to update: %(modules)s.",
                image=image,
                user=user.display_name,
                modules=", ".join(names) or _("none"),
            )
        )
        return True

    @api.model
    def herd_staging_status(self, staging_id):
        """What the CI needs to follow a staging delivery: live images, rollout
        and module update of the last herd_deploy_staging. Nothing else."""
        staging = self.env["k8s.odoo.instance"].sudo().browse(int(staging_id)).exists()
        self._herd_check_can_request(staging)
        if staging.environment != "staging" or not staging.production_instance_id:
            raise UserError(_("Only a staging linked to a production has a delivery status."))
        staging._herd_advance_deploy()
        upgrade = staging.herd_deploy_upgrade_id
        deployed = staging.herd_deploy_image
        return {
            "image": staging._herd_live_image(),
            "production_image": staging.production_instance_id._herd_live_image(),
            "deploy_image": deployed or False,
            "rolled_out": bool(deployed) and staging._herd_rolled_out_safe(deployed),
            "modules": staging.herd_deploy_modules or False,
            "upgrade_state": upgrade.state if upgrade else False,
        }

    @api.model
    def herd_cancel(self, promotion_id):
        promotion = self.sudo().browse(int(promotion_id)).exists()
        self._herd_check_can_operate(promotion.staging_id)
        if promotion.state not in ("requested", "scheduled"):
            raise UserError(_("Only a promotion that has not started can be cancelled."))
        promotion.write({"state": "cancelled", "code_hash": False})
        promotion.message_post(body=_("Cancelled by %s.", self.env.user.display_name))
        return True

    @api.model
    def _herd_check_can_request(self, staging):
        """Request a promotion or read the delivery status: the CI accounts
        listed on the staging (herd_ci_user_ids), then _herd_check_can_operate.
        Only these two façades call it: resync, cancellation and deployment
        stay out of reach of a CI account on a staging closed to agents."""
        if (
            staging
            and staging.environment == "staging"
            and self.env.user in staging.herd_ci_user_ids
        ):
            return
        self._herd_check_can_operate(staging)

    @api.model
    def _herd_check_can_operate(self, staging):
        """Who may resync, request or cancel: managers, the client's users,
        and agents on stagings opened to them."""
        if not staging:
            raise AccessError(_("Unknown instance."))
        user = self.env.user
        prod = staging.production_instance_id or staging
        if user.has_group("odoo_herd.group_k8s_manager"):
            return
        if herd_is_agent(user):
            if staging.herd_agent_allowed and staging.environment == "staging":
                return
            raise AccessError(_("This staging is not opened to agents."))
        if prod._herd_portal_allowed(user):
            return
        raise AccessError(_("You cannot operate this instance."))

    # ------------------------------------------------------------------
    # Human confirmation (private: only reachable from the portal routes
    # and the backend wizard k8s.odoo.promotion.confirm)
    # ------------------------------------------------------------------
    def action_herd_open_confirm(self):
        """Backend button: open the confirmation wizard, for an approver only."""
        self.ensure_one()
        self._herd_check_approver(self.env.user)
        if not self._herd_confirm_method(self.env.user):
            raise UserError(
                _("This production requires two-factor authentication: enable it to approve.")
            )
        wizard = self.env["k8s.odoo.promotion.confirm"].create({"promotion_id": self.id})
        return wizard._reopen()

    def _herd_check_approver(self, user):
        self.ensure_one()
        if herd_is_agent(user):
            raise AccessError(_("An agent can never confirm a promotion."))
        if user not in self.production_id.herd_approver_ids:
            raise AccessError(_("You are not an approver of %s.", self.production_id.display_name))
        if self.state != "requested":
            raise UserError(_("This promotion is no longer awaiting confirmation."))

    def _herd_confirm_method(self, user):
        """How this approver proves being human: the authenticator app when
        two-factor authentication is on (e-mail then refused), the e-mailed
        code otherwise, nothing when the production requires 2FA."""
        self.ensure_one()
        if user.sudo().totp_enabled:
            return "totp"
        if self.production_id.herd_require_2fa:
            return False
        return "email"

    def _herd_code_digest(self, user, code):
        secret = self.env["ir.config_parameter"].sudo().get_str("database.secret")
        payload = f"{self.id}:{user.id}:{self.image}:{code}".encode()
        return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    def _herd_send_code(self, user):
        """E-mail a one-time code to the approver. Only its keyed hash is
        stored. Assumes no agent can read the approver's mailbox."""
        self.ensure_one()
        self._herd_check_approver(user)
        method = self._herd_confirm_method(user)
        if method == "totp":
            raise UserError(_("Confirm with the code of your authenticator app."))
        if not method:
            raise UserError(
                _("This production requires two-factor authentication: enable it to approve.")
            )
        if not user.email:
            raise UserError(_("Your account has no e-mail address."))
        sudo = self.sudo()
        now = fields.Datetime.now()
        if (
            sudo.code_sent_at
            and sudo.code_user_id == user
            and (now - sudo.code_sent_at < CODE_RESEND_DELAY)
        ):
            raise UserError(_("A code was just sent, please wait a minute."))
        code = f"{secrets.randbelow(10**6):06d}"
        sudo.write(
            {
                "code_hash": self._herd_code_digest(user, code),
                "code_user_id": user.id,
                "code_expires_at": now + CODE_TTL,
                "code_sent_at": now,
                "code_attempts": 0,
            }
        )
        body = Markup(
            "<p>{intro}</p><ul><li>{prod}</li><li>{image}</li><li>{modules}</li>"
            "<li>{install}</li>"
            "<li>{when}</li></ul><p style='font-size:24px'><b>{code}</b></p>"
            "<p>{warning}</p>"
        ).format(
            intro=_("Confirmation code for promotion %s:", self.name),
            prod=_("Production: %s", self.production_id.display_name),
            image=_("Image: %s", self.image),
            modules=_("Modules to update: %s", self.modules or _("none")),
            install=_("Modules to install: %s", self.modules_install or _("none")),
            when=_("When: %s", self.scheduled_at or _("right after confirmation")),
            code=escape(code),
            warning=_("Valid 10 minutes. If you did not ask for it, ignore this e-mail."),
        )
        # A bare mail.mail, deleted once sent: no chatter message carries it.
        self.env["mail.mail"].sudo().create(
            {
                "subject": _("Code to confirm %s", self.name),
                "email_to": user.email_formatted,
                "body_html": body,
                "auto_delete": True,
            }
        ).send()
        self.message_post(body=_("Confirmation code sent to %s.", user.display_name))
        return True

    def _herd_check_email_code(self, user, code):
        sudo = self.sudo()
        now = fields.Datetime.now()
        if not sudo.code_hash or sudo.code_user_id != user:
            raise UserError(_("Ask for a confirmation code first."))
        if sudo.code_expires_at < now:
            raise UserError(_("The code has expired, ask for a new one."))
        if sudo.code_attempts >= CODE_MAX_ATTEMPTS:
            raise UserError(_("Too many attempts, ask for a new code."))
        if not hmac.compare_digest(sudo.code_hash, self._herd_code_digest(user, code)):
            # Counted, then reported without raising: an exception would let a
            # savepoint or an RPC rollback erase the attempt.
            sudo.code_attempts += 1
            return False
        return True

    def _herd_check_totp(self, user, code):
        """Odoo's own check: rate limit per user, replay refused
        (totp_last_counter). Needs the HTTP request of the portal route."""
        if not (code.isdigit() and len(code) == 6):
            return False
        try:
            # TOTP.match() compares integers, like the /web/login/totp route
            user.with_user(user)._check_credentials(
                {"type": "totp", "token": int(code), "login": user.login},
                {"interactive": True},
            )
        except AccessDenied as e:
            # wrong, replayed or rate-limited: the rate limit log is kept
            _logger.info("Promotion %s: TOTP refused for %s: %s", self.name, user.login, e)
            return False
        return True

    def _herd_confirm(self, user, code):
        """Confirm as a human approver. Returns False on a wrong code."""
        self.ensure_one()
        self._herd_check_approver(user)
        method = self._herd_confirm_method(user)
        if not method:
            raise UserError(
                _("This production requires two-factor authentication: enable it to approve.")
            )
        code = (code or "").strip()
        checked = (
            self._herd_check_totp(user, code)
            if method == "totp"
            else self._herd_check_email_code(user, code)
        )
        if not checked:
            return False
        sudo = self.sudo()
        now = fields.Datetime.now()
        scheduled = sudo.scheduled_at and sudo.scheduled_at > now
        sudo.write(
            {
                "code_hash": False,
                "code_expires_at": False,
                "confirmed_by_id": user.id,
                "confirmed_at": now,
                "confirm_method": method,
                "state": "scheduled" if scheduled else "requested",
            }
        )
        method_label = dict(self._fields["confirm_method"].selection)[method]
        sudo.message_post(
            body=_(
                "Confirmed by %(user)s (%(method)s).", user=user.display_name, method=method_label
            )
        )
        if not scheduled:
            sudo._herd_start()
        return True

    # ------------------------------------------------------------------
    # Execution: backup → image → module update
    # ------------------------------------------------------------------
    def _herd_set_step(self, state, **vals):
        self.sudo().write(dict(vals, state=state, step_started_at=fields.Datetime.now()))

    def _herd_fail(self, message):
        for promotion in self:
            promotion._herd_set_step("failed", message=message)
            promotion.message_post(body=_("Failed: %s", message))

    def _herd_start(self):
        for promotion in self.sudo():
            if not promotion.confirmed_by_id:
                raise AccessError(_("A promotion only starts once confirmed by a human."))
            prod = promotion.production_id
            busy = promotion.search(
                [
                    ("production_id", "=", prod.id),
                    ("state", "in", RUNNING_STATES),
                    ("id", "!=", promotion.id),
                ],
                limit=1,
            )
            if busy:
                promotion._herd_fail(_("%s is already running on this production.", busy.name))
                continue
            try:
                live = prod._herd_live_image()
            except UserError as e:
                promotion._herd_fail(str(e))
                continue
            if live != promotion.production_image:
                # Deploying now could silently roll back a newer production.
                promotion._herd_fail(
                    _(
                        "Production changed since the request (%(then)s, now %(now)s): "
                        "ask for a new promotion.",
                        then=promotion.production_image or "-",
                        now=live,
                    )
                )
                continue
            try:
                backup = (
                    self.env["k8s.odoo.backup"]
                    .sudo()
                    .create({"instance_id": prod.id, "format": "zip", "with_filestore": True})
                )
            except Exception as e:
                _logger.exception("Backup of %s failed to start", prod.name)
                promotion._herd_fail(_("The backup could not start: %s", e))
                continue
            promotion._herd_set_step("backing_up", backup_id=backup.id, previous_image=live)

    def _herd_on_backup_done(self, ok, message=None):
        for promotion in self.sudo().filtered(lambda p: p.state == "backing_up"):
            if not ok:
                promotion._herd_fail(
                    _("Backup failed, production left untouched: %s", message or "-")
                )
                continue
            prod = promotion.production_id
            try:
                changed = prod._herd_live_image() != promotion.image
                if changed:
                    prod._herd_patch_image(promotion.image)
                prod.with_context(k8s_cluster_values=True).image = promotion.image
            except Exception as e:
                _logger.exception("Image patch of %s failed", prod.name)
                promotion._herd_fail(_("The image could not be applied: %s", e))
                continue
            if not promotion._module_list() and not promotion._module_list("modules_install"):
                promotion._herd_set_step("done", message=_("Image deployed."))
                promotion.message_post(body=_("Production now runs %s.", promotion.image))
                continue
            # The module update must not run while the pods restart on the new
            # image: both would load the registry and the update would time out
            # on its lock (PROMO/0017). The cron starts it once rolled out.
            promotion._herd_set_step("deploying")
            if changed and not promotion._herd_rolled_out():
                continue
            promotion._herd_start_upgrade()

    def _herd_rolled_out(self):
        self.ensure_one()
        try:
            return self.production_id._herd_rollout_done(self.image)
        except Exception:
            _logger.warning("Rollout of %s not readable yet", self.name, exc_info=True)
            return False

    def _herd_start_upgrade(self):
        for promotion in self:
            prod = promotion.production_id
            modules = promotion._module_list()
            installs = promotion._module_list("modules_install")
            try:
                upgrade = (
                    self.env["k8s.odoo.upgrade"]
                    .sudo()
                    .create(
                        {
                            "instance_id": prod.id,
                            "modules": ",".join(modules),
                            "modules_install": ",".join(installs),
                        }
                    )
                )
            except Exception as e:  # noqa: BLE001
                promotion._herd_fail(
                    _(
                        "Image deployed, but the module update could not start "
                        "(previous image: %(prev)s): %(err)s",
                        prev=promotion.previous_image,
                        err=e,
                    )
                )
                continue
            promotion._herd_set_step("upgrading", upgrade_id=upgrade.id)

    def _herd_on_upgrade_done(self, ok, message=None):
        for promotion in self.sudo().filtered(lambda p: p.state == "upgrading"):
            if ok:
                promotion._herd_set_step(
                    "done", message=_("Image deployed, modules updated or installed.")
                )
                promotion.message_post(body=_("Production now runs %s.", promotion.image))
            else:
                promotion._herd_fail(
                    _(
                        "Module update failed (previous image: %(prev)s): %(err)s",
                        prev=promotion.previous_image,
                        err=message or "-",
                    )
                )

    @api.model
    def _cron_herd_promotions(self):
        now = fields.Datetime.now()
        due = self.sudo().search([("state", "=", "scheduled"), ("scheduled_at", "<=", now)])
        due._herd_start()
        deploying = self.sudo().search([("state", "=", "deploying"), ("upgrade_id", "=", False)])
        deploying.filtered(lambda p: p._herd_rolled_out())._herd_start_upgrade()
        self.env["k8s.odoo.instance"].sudo().search(
            [
                ("environment", "=", "staging"),
                ("herd_deploy_modules", "!=", False),
                ("herd_deploy_upgrade_id", "=", False),
            ]
        )._herd_advance_deploy()
        stuck = self.sudo().search(
            [("state", "in", RUNNING_STATES), ("step_started_at", "<", now - STEP_TIMEOUT)]
        )
        stuck._herd_fail(_("No news from the cluster for 6 hours."))
