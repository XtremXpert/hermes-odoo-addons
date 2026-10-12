from odoo import models


class K8sCreateInstanceWizard(models.TransientModel):
    _inherit = "k8s.create.instance.wizard"

    def _build_instance_spec(self, hosts):
        spec = super()._build_instance_spec(hosts)
        # Explicit database name for the instances of a portal request: herd
        # reaches the fresh database by name to secure its admin account.
        db_name = self.env.context.get("herd_database_name")
        if db_name:
            spec["database"] = dict(spec.get("database") or {}, name=db_name)
        return spec
