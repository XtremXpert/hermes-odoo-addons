from odoo import models


class K8sOdooBackup(models.Model):
    _inherit = "k8s.odoo.backup"

    def _herd_promotions(self):
        return self.env["k8s.odoo.promotion"].sudo().search([("backup_id", "in", self.ids)])

    def mark_completed(self, completion_time=None, message=None, object_key=None):
        res = super().mark_completed(
            completion_time=completion_time, message=message, object_key=object_key
        )
        self._herd_promotions()._herd_on_backup_done(True)
        return res

    def mark_failed(self, message=None, completion_time=None):
        res = super().mark_failed(message=message, completion_time=completion_time)
        self._herd_promotions()._herd_on_backup_done(False, message)
        return res


class K8sOdooUpgrade(models.Model):
    _inherit = "k8s.odoo.upgrade"

    def _herd_promotions(self):
        return self.env["k8s.odoo.promotion"].sudo().search([("upgrade_id", "in", self.ids)])

    def mark_completed(self, completion_time=None, message=None):
        res = super().mark_completed(completion_time=completion_time, message=message)
        self._herd_promotions()._herd_on_upgrade_done(True)
        return res

    def mark_failed(self, message=None, completion_time=None):
        res = super().mark_failed(message=message, completion_time=completion_time)
        self._herd_promotions()._herd_on_upgrade_done(False, message)
        return res
