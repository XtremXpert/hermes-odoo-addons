import logging

from odoo import models

_logger = logging.getLogger(__name__)

# Paramètre posé par `odoo neutralize` (cœur Odoo) sur les copies de staging.
PARAM = "database.is_neutralized"


class IrCron(models.Model):
    _inherit = "ir.cron"

    def _is_neutralized(self):
        return self.env["ir.config_parameter"].sudo().get_bool(PARAM)

    def _callback(self, cron_name, server_action_id):
        """Refuser toute exécution sur une base neutralisée.

        Le cœur d'Odoo neutralise en désactivant les crons au moment du
        resync, et garde `toggle` contre une réactivation par effet de bord —
        mais ni `_callback` ni `method_direct_trigger` ne consultent le
        paramètre. Une installation de module recrée les crons actifs, et un
        clic sur « Exécuter manuellement » les lance dans le thread HTTP.

        Ce garde-fou couvre les trois voies : planificateur, bouton manuel et
        appel programmatique, puisque les trois passent par ici.
        """
        if self._is_neutralized():
            _logger.info(
                "Cron %s ignoré : base neutralisée (%s).", cron_name, PARAM
            )
            return False
        return super()._callback(cron_name, server_action_id)
