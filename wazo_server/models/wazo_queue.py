# Part of the wazo_server Odoo module. See LICENSE for details.
"""La ressource peut viser un tenant précis (voir le mixin de sélection)."""

from odoo import models


class WazoSelectionOverride(models.Model):
    _name = "wazo.queue"
    # La première entrée de `_inherit` l'emporte : le mixin doit
    # précéder le modèle étendu, sinon la chaîne de wazo_tenant gagne
    # et les réglages décident à la place du tenant choisi. Mesuré.
    _inherit = ["wazo.server.tenant.selection", "wazo.queue"]
