# Copyright 2025 Bemade
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import json
import logging

from kubernetes import client

from odoo import http
from odoo.http import Response
from odoo.http import request

_logger = logging.getLogger(__name__)


class K8sUpgradeWebhook(http.Controller):
    """Controller to receive upgrade status webhooks from the Kubernetes operator."""

    @http.route(
        "/k8s/upgrade/webhook/<int:upgrade_id>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def upgrade_webhook(self, upgrade_id, **kwargs):
        """Receive upgrade status update from the operator.

        Expected JSON payload:
        {
            "phase": "Running" | "Completed" | "Failed",
            "jobName": "instance-upgrade-xyz",
            "message": "optional status/error message",
            "completionTime": "optional ISO-8601 timestamp"
        }

        Authorization: Bearer <webhook_token>
        """
        # Validate Authorization header
        auth_header = request.httprequest.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            _logger.warning(
                "Upgrade webhook %s: missing or invalid Authorization header",
                upgrade_id,
            )
            return Response(
                json.dumps({"error": "Unauthorized"}),
                status=401,
                content_type="application/json",
            )

        token = auth_header[7:]  # Strip "Bearer "

        # Find the upgrade record
        upgrade = request.env["k8s.odoo.upgrade"].sudo().browse(upgrade_id)
        if not upgrade.exists():
            _logger.warning("Upgrade webhook: upgrade %s not found", upgrade_id)
            return Response(
                json.dumps({"error": "Upgrade not found"}),
                status=404,
                content_type="application/json",
            )

        # Validate token
        if not upgrade.webhook_token or upgrade.webhook_token != token:
            _logger.warning("Upgrade webhook %s: invalid token", upgrade_id)
            return Response(
                json.dumps({"error": "Invalid token"}),
                status=403,
                content_type="application/json",
            )

        # Parse JSON payload
        try:
            data = json.loads(request.httprequest.data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            _logger.warning("Upgrade webhook %s: invalid JSON: %s", upgrade_id, e)
            return Response(
                json.dumps({"error": "Invalid JSON payload"}),
                status=400,
                content_type="application/json",
            )

        phase = data.get("phase", "").lower()
        message = data.get("message")
        job_name = data.get("jobName")

        _logger.info(
            "Upgrade webhook %s: received phase=%s, jobName=%s",
            upgrade.name,
            phase,
            job_name,
        )

        # L'opérateur dépose la queue du journal dans le CR ; le webhook peut
        # arriver avant que le champ ne soit posé. Une lecture du CR, sans échec
        # bloquant, récupère ce qui est disponible.
        try:
            resource = (
                client.CustomObjectsApi(upgrade.cluster_id._get_k8s_client())
                .get_namespaced_custom_object(
                    group="bemade.org",
                    version="v1alpha1",
                    namespace=upgrade.instance_id.namespace,
                    plural="odooupgradejobs",
                    name=upgrade.upgrade_job_name,
                )
            )
            upgrade._k8s_job_prendre_journal((resource.get("status") or {}).get("logTail"))
        except Exception as e:  # noqa: BLE001 — le journal ne doit pas bloquer le flux
            _logger.info("Upgrade webhook %s: journal non récupéré (%s)", upgrade_id, e)

        # Update upgrade record based on phase
        if phase == "running":
            upgrade.mark_running(job_name=job_name)
        elif phase == "completed":
            upgrade.mark_completed(
                completion_time=data.get("completionTime"),
                message=message,
            )
        elif phase == "failed":
            upgrade.mark_failed(
                message=message or "Upgrade failed",
                completion_time=data.get("completionTime"),
            )
        else:
            _logger.warning("Upgrade webhook %s: unknown phase %s", upgrade_id, phase)

        return Response(
            json.dumps({"status": "ok"}),
            status=200,
            content_type="application/json",
        )
