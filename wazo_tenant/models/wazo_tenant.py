# Part of the wazo_tenant Odoo module. See LICENSE for details.
"""Les tenants Wazo que l'instance peut voir.

Chaque fiche reflète un tenant de l'API : la liste est alimentée par
``action_sync_from_wazo``, qui interroge ``GET /tenants`` avec le jeton
configuré. La portée dépend du jeton — un jeton de tenant ne voit que son
propre tenant, le jeton maître les voit tous. Sur une instance de tenant,
il n'y a donc en pratique qu'une fiche, retenue comme le tenant configuré ;
sur l'instance de l'exploitant, la liste en montre plusieurs et le champ
des réglages laisse choisir lequel cette instance parle.
"""

from odoo import fields
from odoo import models
from odoo.addons.wazo_tenant.services.wazo_client import WazoAPIError
from odoo.exceptions import UserError


class WazoTenant(models.Model):
    _name = "wazo.tenant"
    _description = "Tenant Wazo visible de cette instance"
    _rec_name = "name"
    _order = "name"

    name = fields.Char(string="Nom", required=True, readonly=True)
    slug = fields.Char(string="Identifiant", readonly=True)
    remote_uuid = fields.Char(
        string="UUID Wazo", required=True, readonly=True, copy=False, index=True
    )
    is_configured = fields.Boolean(
        string="Tenant configuré",
        compute="_compute_is_configured",
        inverse="_inverse_is_configured",
        store=False,
        help="Tenant que cette instance adresse. Un seul à la fois : "
        "en sélectionner un retire le précédent.",
    )
    last_seen_at = fields.Datetime(string="Vu le", readonly=True, copy=False)

    _remote_uuid_uniq = models.Constraint("unique(remote_uuid)", "Ce tenant est déjà connu.")

    # ------------------------------------------------------------------
    # Synchronisation
    # ------------------------------------------------------------------

    def action_sync_from_wazo(self):
        """Liste les tenants visibles du jeton configuré.

        Le jeton d'un tenant ne lit que lui-même — la liste produite a
        alors une fiche, retenue d'office. Le jeton maître les voit tous :
        rien n'est sélectionné pour lui, c'est un choix à poser.
        """
        client = self._client()
        try:
            reponse = client.auth("GET", "/tenants") or {}
        except WazoAPIError as error:
            raise UserError(str(error)) from error
        items = reponse.get("items") or []
        vus = set()
        for item in items:
            uuid = item.get("uuid")
            if not uuid:
                continue
            vus.add(uuid)
            fiche = self.search([("remote_uuid", "=", uuid)], limit=1)
            if fiche:
                fiche.write(
                    {
                        "name": item.get("name"),
                        "slug": item.get("slug"),
                        "last_seen_at": fields.Datetime.now(),
                    }
                )
            else:
                self.create(
                    {
                        "name": item.get("name") or item.get("slug"),
                        "slug": item.get("slug"),
                        "remote_uuid": uuid,
                        "last_seen_at": fields.Datetime.now(),
                    }
                )
        # Un seul tenant visible : c'est lui le tenant configuré.
        if len(vus) == 1:
            self.env["ir.config_parameter"].sudo().set_str("wazo.tenant_id", vus.pop())
        return len(items)

    def _client(self):
        """Client des réglages — la portée de la liste est celle du jeton."""
        from odoo.addons.wazo_tenant.services.wazo_client import WazoClient

        return WazoClient(self.env)

    # ------------------------------------------------------------------
    # Tenant configuré
    # ------------------------------------------------------------------

    def _compute_is_configured(self):
        param = self.env["ir.config_parameter"].sudo().get_str("wazo.tenant_id")
        for fiche in self:
            fiche.is_configured = fiche.remote_uuid and fiche.remote_uuid == param

    def _inverse_is_configured(self):
        param = self.env["ir.config_parameter"].sudo()
        for fiche in self:
            if fiche.is_configured:
                param.set_str("wazo.tenant_id", fiche.remote_uuid)
            else:
                # Décoché : plus de tenant configuré — vide, pas orphelin.
                if param.get_str("wazo.tenant_id") == fiche.remote_uuid:
                    param.set_str("wazo.tenant_id", False)
