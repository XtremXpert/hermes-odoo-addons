from odoo import _
from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import ValidationError

from .k8s_odoo_instance_request import HOST_SUFFIX_RE
from .k8s_odoo_instance_request import NAMESPACE_RE


class K8sOdooInstanceTemplate(models.Model):
    _inherit = "k8s.odoo.instance.template"

    herd_portal_published = fields.Boolean(
        string="Offered in the portal",
        help="Clients without an Odoo database may request one from this offer, "
        "from the portal. A cluster manager approves each request.",
    )
    herd_portal_description = fields.Text(
        string="Portal description",
        translate=True,
        help="What the client reads about this offer in the portal.",
    )
    herd_cluster_id = fields.Many2one(
        "k8s.cluster",
        string="Cluster",
        help="Cluster where the databases requested from this offer are created.",
    )
    herd_namespace = fields.Char(
        string="Namespace",
        help="Namespace for the databases of this offer. It must already exist, "
        "with the image pull secret and the Role letting odoo-herd reach its "
        "services (deploy/odoo-herd-clients.yaml).",
    )
    herd_host_suffix = fields.Char(
        string="Host suffix",
        help="Domain under which the hosts are made: <name>.<suffix> for the "
        "production, <name>-staging.<suffix> for its staging. A wildcard DNS "
        "record must point it to the cluster ingress.",
    )

    @api.constrains(
        "herd_portal_published", "herd_cluster_id", "herd_namespace", "herd_host_suffix"
    )
    def _check_herd_portal_offer(self):
        for template in self.filtered("herd_portal_published"):
            if not template.herd_cluster_id:
                raise ValidationError(_("An offer published in the portal needs a cluster."))
            if not NAMESPACE_RE.match(template.herd_namespace or ""):
                raise ValidationError(_("Invalid namespace: %s", template.herd_namespace or "-"))
            if not HOST_SUFFIX_RE.match(template.herd_host_suffix or ""):
                raise ValidationError(
                    _("Invalid host suffix: %s", template.herd_host_suffix or "-")
                )
