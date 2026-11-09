from odoo import models


class K8sOdooBackup(models.Model):
    _inherit = "k8s.odoo.backup"

    def _herd_promotions(self):
        return self.env["k8s.odoo.promotion"].sudo().search([("backup_id", "in", self.ids)])

    def mark_completed(self, completion_time=None, message=None, object_key=None):
        """Passe la sauvegarde à « completed » et prévient la promotion qui l'attend.

        Args:
            completion_time (datetime, optional): heure de fin du job.
            message (str, optional): message à conserver.
            object_key (str, optional): clé de l'objet stocké.

        Returns:
            bool: résultat de la mise à jour parente.
        """
        res = super().mark_completed(
            completion_time=completion_time, message=message, object_key=object_key
        )
        self._herd_promotions()._herd_on_backup_done(True)
        return res

    def mark_failed(self, message=None, completion_time=None):
        """Passe la sauvegarde à « failed » et signale l'échec à la promotion.

        Args:
            message (str, optional): cause de l'échec.
            completion_time (datetime, optional): heure de fin du job.

        Returns:
            bool: résultat de la mise à jour parente.
        """
        res = super().mark_failed(message=message, completion_time=completion_time)
        self._herd_promotions()._herd_on_backup_done(False, message)
        return res


class K8sOdooUpgrade(models.Model):
    _inherit = "k8s.odoo.upgrade"

    def _herd_promotions(self):
        return self.env["k8s.odoo.promotion"].sudo().search([("upgrade_id", "in", self.ids)])

    def mark_completed(self, completion_time=None, message=None):
        """Passe la mise à jour à « completed » et prévient la promotion qui l'attend.

        Args:
            completion_time (datetime, optional): heure de fin du job.
            message (str, optional): message à conserver.

        Returns:
            bool: résultat de la mise à jour parente.
        """
        res = super().mark_completed(completion_time=completion_time, message=message)
        self._herd_promotions()._herd_on_upgrade_done(True)
        return res

    def mark_failed(self, message=None, completion_time=None):
        """Passe la mise à jour à « failed » et signale l'échec à la promotion.

        Args:
            message (str, optional): cause de l'échec.
            completion_time (datetime, optional): heure de fin du job.

        Returns:
            bool: résultat de la mise à jour parente.
        """
        res = super().mark_failed(message=message, completion_time=completion_time)
        self._herd_promotions()._herd_on_upgrade_done(False, message)
        return res
