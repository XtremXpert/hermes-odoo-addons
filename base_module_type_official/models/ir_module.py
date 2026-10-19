import logging

from odoo import api
from odoo import models

_logger = logging.getLogger(__name__)


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def _register_hook(self):
        super()._register_hook()
        self._fill_missing_module_type()

    @api.model
    def _fill_missing_module_type(self):
        """Donne « official » aux modules dont le type est resté vide.

        Un module enregistré pendant un démarrage qui met la base à jour
        (``-i``, ``-u``, nouveau paquet Odoo) l'est avant le chargement de
        ``base_import_module`` : le défaut de ``module_type`` ne s'applique pas
        et la colonne reste NULL. Le panneau de l'écran Applications filtre
        toujours sur « official » ou « industries », donc ces modules n'y
        apparaissent jamais. ``_register_hook`` passe une fois le registre
        complet chargé, après chacun de ces démarrages. Les modules
        « industries » ne sont pas touchés.
        """
        self.env.cr.execute(
            "UPDATE ir_module_module SET module_type = 'official' WHERE module_type IS NULL"
        )
        count = self.env.cr.rowcount
        if count:
            self.invalidate_model(["module_type"])
            _logger.info("module_type « official » donné à %s module(s)", count)
        return count
