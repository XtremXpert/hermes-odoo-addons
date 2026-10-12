"""Operator jobs (upgrade, backup, restore, staging refresh) as custom resources.

Two guarantees shared by the four models:

* the custom resource is created **after the transaction commits**. Odoo retries
  a transaction after a serialization conflict: creating the resource inside it
  launched one more job on the cluster at each retry (three concurrent module
  upgrades on the same database, one of them failing on the registry lock);
* the job state is **read back from the cluster** by a scheduled action, so a
  record no longer waits forever when the operator's webhook is lost (typically
  when Odoo restarts at the end of an upgrade it triggered).
"""

import logging
from datetime import timedelta

from kubernetes import client
from kubernetes.client.rest import ApiException

from odoo import _
from odoo import api
from odoo import fields
from odoo import models

_logger = logging.getLogger(__name__)

# A webhook usually arrives within seconds: only read back older records.
POLL_DELAY = timedelta(minutes=2)
# A record still without custom resource after this delay will never get one.
CREATION_TIMEOUT = timedelta(minutes=15)
OPEN_STATES = ("pending", "running")


class K8sJobMixin(models.AbstractModel):
    _name = "k8s.job.mixin"
    _description = "Operator job created after commit and read back from the cluster"

    # Set by each model.
    _k8s_job_plural = None  # e.g. "odooupgradejobs"
    _k8s_job_cr_field = None  # field holding the custom resource name
    _k8s_job_create_method = None  # method creating the custom resource
    _k8s_job_instance_field = "instance_id"  # instance whose namespace hosts it

    # ------------------------------------------------------------------
    # Creation after commit
    # ------------------------------------------------------------------
    def _k8s_job_create_after_commit(self):
        """Create the custom resources once the current transaction commits."""
        if not self:
            return
        model, ids = self._name, self.ids
        registry, uid, context = self.env.registry, self.env.uid, dict(self.env.context)
        # Same rights as the caller: a promotion confirmed from the portal
        # creates its backup in sudo, which the new environment must keep.
        su = self.env.su

        def create_custom_resources():
            with registry.cursor() as cr:
                env = api.Environment(cr, uid, context, su=su)
                env[model].browse(ids).exists()._k8s_job_create_now()

        self.env.cr.postcommit.add(create_custom_resources)

    def _k8s_job_create_now(self):
        for record in self:
            if record.state != "pending" or record[record._k8s_job_cr_field]:
                continue  # already created, or no longer waiting for it
            try:
                with self.env.cr.savepoint():
                    getattr(record, record._k8s_job_create_method)()
            except Exception as e:
                _logger.exception("Kubernetes job of %s could not be created", record.display_name)
                record.mark_failed(message=_("The Kubernetes job could not be created: %s", e))

    # ------------------------------------------------------------------
    # Read back from the cluster
    # ------------------------------------------------------------------
    def _k8s_job_instance(self):
        return self[self._k8s_job_instance_field]

    def _k8s_job_apply_status(self, data):
        """Same handling as the operator's webhook for this model.

        ``data`` has the webhook's keys: phase, message, completionTime, …"""
        phase = (data.get("phase") or "").lower()
        if phase == "running" and self.state == "pending":
            self.mark_running()
        elif phase == "completed":
            self.mark_completed(
                completion_time=data.get("completionTime"), message=data.get("message")
            )
        elif phase == "failed":
            self.mark_failed(
                message=data.get("message") or _("The Kubernetes job failed."),
                completion_time=data.get("completionTime"),
            )

    @api.model
    def _k8s_job_poll(self):
        """Read back jobs still open after POLL_DELAY (scheduled action)."""
        now = fields.Datetime.now()
        records = self.search([("state", "in", OPEN_STATES), ("write_date", "<", now - POLL_DELAY)])
        for record in records:
            try:
                with self.env.cr.savepoint():
                    record._k8s_job_poll_one(now)
            except Exception:
                _logger.exception("Could not read back %s", record.display_name)

    def _k8s_job_poll_one(self, now):
        self.ensure_one()
        name = self[self._k8s_job_cr_field]
        if not name:
            if self.create_date < now - CREATION_TIMEOUT:
                self.mark_failed(message=_("The Kubernetes job was never created."))
            return
        instance = self._k8s_job_instance()
        cluster = instance.cluster_id
        if not cluster.active:
            return
        custom_api = client.CustomObjectsApi(cluster._get_k8s_client())
        try:
            resource = custom_api.get_namespaced_custom_object(
                group="bemade.org",
                version="v1alpha1",
                namespace=instance.namespace,
                plural=self._k8s_job_plural,
                name=name,
            )
        except ApiException as e:
            if e.status == 404:
                self.mark_failed(message=_("The Kubernetes job %s no longer exists.", name))
                return
            raise
        status = resource.get("status") or {}
        if status.get("phase"):
            self._k8s_job_apply_status(status)
