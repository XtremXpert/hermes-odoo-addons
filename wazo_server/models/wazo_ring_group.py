# Part of the wazo_server Odoo module. See LICENSE for details.
"""Le groupe d'appel vise le même tenant que ses membres (voir le mixin)."""

from odoo import models


class WazoRingGroup(models.Model):
    _name = "wazo.ring.group"
    # Voir wazo_user.py : la première entrée de `_inherit` l'emporte.
    _inherit = ["wazo.server.tenant.selection", "wazo.ring.group"]
