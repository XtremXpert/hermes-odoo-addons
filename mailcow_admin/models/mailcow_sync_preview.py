# Part of the mailcow_admin Odoo module. See LICENSE for details.
from odoo import fields, models


class MailcowSyncPreview(models.TransientModel):
    """Ce qu'une synchronisation changerait, décrit sans rien écrire."""

    _name = 'mailcow.sync.preview'
    _description = 'Mailcow : aperçu de synchronisation'

    model_name = fields.Char(string='Objet', readonly=True)
    plan = fields.Text(string='Changements à venir', readonly=True)
