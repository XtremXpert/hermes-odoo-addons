import logging

from kubernetes import client

from odoo import SUPERUSER_ID
from odoo import _
from odoo import fields
from odoo import models
from odoo.exceptions import AccessError
from odoo.exceptions import UserError

from .k8s_odoo_promotion import herd_is_agent

_logger = logging.getLogger(__name__)

# Fields an agent must never change, whatever its access rights.
AGENT_FORBIDDEN_FIELDS = {
    "environment",
    "production_instance_id",
    "herd_partner_id",
    "herd_approver_ids",
    "herd_agent_allowed",
    "herd_ci_user_ids",
    "herd_require_2fa",
    "herd_deploy_image",
    "herd_deploy_modules",
    "herd_deploy_upgrade_id",
}


class K8sOdooInstance(models.Model):
    _inherit = "k8s.odoo.instance"

    herd_partner_id = fields.Many2one(
        "res.partner",
        string="Client",
        tracking=True,
        help="Client whose portal users see this production and its stagings.",
    )
    herd_approver_ids = fields.Many2many(
        "res.users",
        "k8s_odoo_instance_herd_approver_rel",
        "instance_id",
        "user_id",
        string="Production approvers",
        help="Humans who may confirm a promotion to this production, from the "
        "portal, with a code sent by e-mail. Agents are always refused.",
    )
    herd_require_2fa = fields.Boolean(
        string="Require two-factor authentication",
        tracking=True,
        help="Production only: approvers must confirm with their authenticator app "
        "(two-factor authentication on their account); the e-mailed code is refused.",
    )
    herd_agent_allowed = fields.Boolean(
        string="Open to agents",
        tracking=True,
        help="Staging only: agents (staging operators) may deploy code on it, "
        "resync it and request a promotion of its image.",
    )
    herd_ci_user_ids = fields.Many2many(
        "res.users",
        "k8s_odoo_instance_herd_ci_user_rel",
        "instance_id",
        "user_id",
        string="CI accounts",
        tracking=True,
        help="Staging only: these accounts (a CI) may request a promotion of its "
        "image and read its delivery status, even when it is not open to agents. "
        "Nothing else: no deployment, no resync, no cancellation, never a "
        "confirmation.",
    )
    herd_staging_ids = fields.One2many(
        "k8s.odoo.instance", "production_instance_id", string="Stagings"
    )
    herd_promotion_ids = fields.One2many("k8s.odoo.promotion", "production_id", string="Promotions")
    # Last delivery of a staging through herd_deploy_staging (the CI): its
    # module update starts once the image is rolled out (_herd_advance_deploy).
    herd_deploy_image = fields.Char(string="Delivered image", readonly=True, copy=False)
    herd_deploy_modules = fields.Char(string="Delivered modules", readonly=True, copy=False)
    herd_deploy_upgrade_id = fields.Many2one(
        "k8s.odoo.upgrade", string="Delivery module update", readonly=True, copy=False
    )

    def write(self, vals):
        if herd_is_agent(self.env.user):
            forbidden = AGENT_FORBIDDEN_FIELDS & set(vals)
            if "image" in vals and any(i.environment == "production" for i in self):
                forbidden.add("image")
            if forbidden:
                raise AccessError(
                    _("Agents cannot change %s on these instances.", ", ".join(sorted(forbidden)))
                )
        res = super().write(vals)
        if "phase" in vals:
            self._herd_wake_requests()
        return res

    def _herd_wake_requests(self):
        """A phase change (webhook or sync) may let a database request move on:
        run its step in a cron worker, out of the webhook transaction."""
        pending = (
            self.env["k8s.odoo.instance.request"]
            .sudo()
            .search_count(
                [
                    ("state", "in", ("creating", "cloning")),
                    "|",
                    ("production_id", "in", self.ids),
                    ("staging_id", "in", self.ids),
                ],
                limit=1,
            )
        )
        if pending:
            self.env.ref("odoo_herd_portal.cron_herd_requests").sudo()._trigger()

    def _build_patch_data(self):
        """A production image only changes through a confirmed promotion,
        never through "Sync to Cluster"."""
        self.ensure_one()
        if self.environment == "production" and "image" in self._edited_field_names():
            raise UserError(
                _(
                    "The image of %s only changes through a confirmed promotion "
                    '(Odoo Herd → Promotions). Use "Reset to Current" to drop this change.',
                    self.display_name,
                )
            )
        return super()._build_patch_data()

    def _herd_deploy_write(self, vals):
        """Write the delivery fields, which agents may not write themselves:
        as the superuser, from server code only (RPC callers only control the
        context, never the user)."""
        self.with_user(SUPERUSER_ID).with_context(k8s_cluster_values=True).write(vals)

    def _herd_rolled_out_safe(self, image):
        try:
            return self._herd_rollout_done(image)
        except Exception:
            _logger.warning("Rollout of %s not readable yet", self.name, exc_info=True)
            return False

    def _herd_advance_deploy(self):
        """Start the module update of a staging delivery once its image is
        rolled out. Called by the cron and by herd_staging_status."""
        for staging in self.sudo():
            if (
                staging.environment != "staging"
                or not staging.herd_deploy_modules
                or staging.herd_deploy_upgrade_id
                or not staging._herd_rolled_out_safe(staging.herd_deploy_image)
            ):
                continue
            upgrade = (
                self.env["k8s.odoo.upgrade"]
                .sudo()
                .create({"instance_id": staging.id, "modules": staging.herd_deploy_modules})
            )
            staging._herd_deploy_write({"herd_deploy_upgrade_id": upgrade.id})
            staging.message_post(
                body=_(
                    "Module update %(upgrade)s started: %(modules)s.",
                    upgrade=upgrade.display_name,
                    modules=staging.herd_deploy_modules,
                )
            )

    def _herd_portal_allowed(self, user):
        """Portal visibility of a production: its client's users, its
        approvers and the cluster managers."""
        self.ensure_one()
        if self.environment != "production":
            return False
        if user in self.herd_approver_ids or user.has_group("odoo_herd.group_k8s_manager"):
            return True
        partner = self.herd_partner_id.commercial_partner_id
        return bool(partner) and user.partner_id.commercial_partner_id == partner

    def _herd_live_image(self):
        """Image the cluster actually runs (spec.image, read live). The stored
        `image` field is the desired configuration of odoo_herd: a sync does not
        update it, so it can lag behind a change made on the cluster."""
        self.ensure_one()
        image = self.current_image
        if not image:
            raise UserError(
                _(
                    "Cannot read the image of %s from the cluster, try again later.",
                    self.display_name,
                )
            )
        return image

    def _herd_rollout_done(self, image):
        """Whether the cluster has rolled ``image`` out: it is spec.image and
        the Ready condition of the current generation is True (the operator
        has seen the change and the pods are back on the new image)."""
        self.ensure_one()
        if not self.cluster_id.active:
            return False
        custom_api = client.CustomObjectsApi(self.cluster_id._get_k8s_client())
        obj = custom_api.get_namespaced_custom_object(
            group="bemade.org",
            version="v1alpha1",
            namespace=self.namespace,
            plural="odooinstances",
            name=self.name,
        )
        if (obj.get("spec") or {}).get("image") != image:
            return False
        generation = (obj.get("metadata") or {}).get("generation") or 0
        for condition in (obj.get("status") or {}).get("conditions") or []:
            if condition.get("type") == "Ready":
                return (
                    condition.get("status") == "True"
                    and (condition.get("observedGeneration") or 0) >= generation
                )
        return False

    def _herd_patch_image(self, image):
        """Patch only spec.image: _patch_to_cluster() would also ship every
        other editable field not yet synced."""
        self.ensure_one()
        if herd_is_agent(self.env.user) and self.environment == "production":
            raise AccessError(_("Agents cannot change a production image."))
        if not self.cluster_id.active:
            raise UserError(_("Cluster %s is not active.", self.cluster_id.display_name))
        custom_api = client.CustomObjectsApi(self.cluster_id._get_k8s_client())
        custom_api.patch_namespaced_custom_object(
            group="bemade.org",
            version="v1alpha1",
            namespace=self.namespace,
            plural="odooinstances",
            name=self.name,
            body={"spec": {"image": image}},
        )
        _logger.info("Image of %s/%s set to %s", self.namespace, self.name, image)
