# Part of the mailcow_tenant Odoo module. See LICENSE for details.
from odoo import fields
from odoo import models


class MailcowEmailAddress(models.Model):
    _name = "mailcow.email_address"
    _description = "Mailcow: adresse courriel"
    _order = "address"

    address = fields.Char(string="Adresse", required=True, index=True)
    comment = fields.Char(string="Commentaire")

    _check_address_unique = models.Constraint("unique(address)", "Cette adresse existe déjà.")
