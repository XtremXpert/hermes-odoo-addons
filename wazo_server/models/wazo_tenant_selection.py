# Part of the wazo_server Odoo module. See LICENSE for details.
"""Choisir le tenant administré, fiche par fiche.

Sur l'instance de l'**exploitant**, plusieurs tenants cohabitent : le tenant
unique des réglages ne peut plus être celui de tout le monde. Le champ ajouté
par ce mixin décide, pour **cette** fiche, de l'en-tête ``Wazo-Tenant`` et du
contexte employés — le client et le contexte étant fournis par le mixin de
``wazo_phone`` (``_wazo_tenant_uuid``, ``_wazo_line_context``), que l'on étend
ici plutôt que de le modifier.

Sans choix — fiche créée avant ce champ, ou tenant pas encore créé sur Wazo —,
on retombe sur les réglages. C'est ce qui permet à un tenant d'installer
`wazo_phone` seul : le champ n'existe alors nulle part.
"""

from odoo import fields
from odoo import models


class WazoServerTenantSelection(models.AbstractModel):
    _name = "wazo.server.tenant.selection"
    _description = "Fiche Wazo rattachée à un tenant"

    tenant_id = fields.Many2one(
        "wazo.server.tenant",
        string="Tenant Wazo",
        ondelete="restrict",
        index=True,
        copy=False,
        groups="wazo_phone.group_wazo_manager",
        help="Tenant à administrer pour cette fiche. Laissé vide, c'est le "
        "tenant des réglages qui est utilisé.",
    )

    def _valeur_du_tenant(self, champ):
        """La valeur d'un champ du tenant choisi, ou ``None``.

        Une fiche sans tenant, ou dont le tenant n'a pas encore la valeur
        demandée (pas encore créé sur Wazo), rend ``None`` : à l'appelant de
        retomber sur les réglages. Sur un jeu d'enregistrements vide — c'est le
        cas de l'inventaire, qui interroge le modèle sans fiche — la boucle ne
        rend rien, donc les réglages s'appliquent aussi.
        """
        for fiche in self:
            if fiche.tenant_id and fiche.tenant_id[champ]:
                return fiche.tenant_id[champ]
        return None

    def _wazo_tenant_uuid(self):
        """En-tête ``Wazo-Tenant`` : le tenant choisi, sinon les réglages."""
        return self._valeur_du_tenant("remote_uuid") or super()._wazo_tenant_uuid()

    def _wazo_line_context(self):
        """Contexte des postes : celui du tenant choisi, sinon les réglages."""
        return self._valeur_du_tenant("remote_context_name") or super()._wazo_line_context()
