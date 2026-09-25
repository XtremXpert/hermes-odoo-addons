# Part of the mailcow_admin Odoo module. See LICENSE for details.
from odoo import fields, models


class MailcowSyncMixin(models.AbstractModel):
    """Ce que les trois objets Mailcow partagent.

    La date de dernière synchronisation est ce qui distingue une fiche
    DISPARUE du serveur (on l'y avait vue, Mailcow ne la liste plus) d'une
    fiche JAMAIS POUSSÉE (elle n'a jamais existé que dans Odoo). Sans elle,
    les deux se ressemblent — et on ne nettoie pas de la même façon.
    """

    _name = 'mailcow.sync.mixin'
    _description = 'Mailcow : suivi de synchronisation'

    last_synced_on = fields.Datetime(
        string='Dernière synchronisation', readonly=True)

    def action_forget_locally(self):
        """Retirer la fiche locale sans toucher au serveur.

        On archive plutôt que de supprimer : la fiche sort de la vue, mais
        l'historique reste consultable si on s'est trompé.
        """
        self.write({'active': False})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success', 'title': 'Mailcow', 'sticky': False,
                'message': '%d fiche(s) archivée(s). Le serveur n\'a pas été '
                           'touché.' % len(self),
            },
        }

    def action_purge_local(self):
        """Supprimer définitivement la fiche locale.

        Le serveur n'est jamais touché : c'est le nettoyage d'un reste local,
        pas une suppression de boîte.
        """
        nombre = len(self)
        self.unlink()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success', 'title': 'Mailcow', 'sticky': False,
                'message': '%d fiche(s) supprimée(s) d\'Odoo. Le serveur n\'a pas '
                           'été touché.' % nombre,
            },
        }
