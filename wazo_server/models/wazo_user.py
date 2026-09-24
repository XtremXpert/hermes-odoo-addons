# Part of the wazo_server Odoo module. See LICENSE for details.
"""Le poste Wazo peut viser un tenant précis (voir le mixin de sélection)."""

from odoo import models


class WazoUser(models.Model):
    _name = 'wazo.user'
    # La première entrée de `_inherit` l'emporte : le mixin doit précéder le
    # modèle dont on étend les méthodes, sinon `wazo.extension.mixin` (placé
    # par `wazo.user` dans la chaîne) gagne et les réglages décident. Mesuré.
    _inherit = ['wazo.server.tenant.selection', 'wazo.user']
