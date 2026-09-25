# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Contact Odoo : création d'utilisateur Wazo et statistiques d'appels."""

import re

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    wazo_user_id = fields.Many2one(
        'wazo.user', string='Utilisateur Wazo', ondelete='set null',
        help='Utilisateur Wazo associé à ce contact.')
    wazo_cdr_ids = fields.One2many('wazo.cdr', 'partner_id')
    wazo_cdr_count = fields.Integer(
        string='Nombre d\'appels', compute='_compute_wazo_cdr_count')
    wazo_extension = fields.Char(
        string='Poste Wazo', compute='_compute_wazo_extension')

    @api.depends('wazo_cdr_ids')
    def _compute_wazo_cdr_count(self):
        for partner in self:
            partner.wazo_cdr_count = len(partner.wazo_cdr_ids)

    @api.depends('wazo_user_id.extension')
    def _compute_wazo_extension(self):
        for partner in self:
            partner.wazo_extension = (
                partner.wazo_user_id.extension or '')

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @api.model
    def action_create_wazo_user(self):
        """Crée l'utilisateur Wazo du contact (contact unique)."""
        partner = self.ensure_one()
        if partner.wazo_user_id:
            raise UserError(
                'Le contact %s a déjà un utilisateur Wazo.' % partner.name)
        digits = re.sub(r'\D', '', partner.phone or '')
        if not digits:
            raise UserError(
                'Le numéro de téléphone du contact %s est requis pour '
                'créer son poste Wazo.' % partner.name)
        wazo_user = self.env['wazo.user'].create({
            'name': partner.name,
            'partner_id': partner.id,
            'extension': digits,
            'wazo_state': 'new',
        })
        partner.write({'wazo_user_id': wazo_user.id})
        wazo_user.action_sync_wazo()

    def action_open_wazo_user(self):
        """Ouvre l'utilisateur Wazo du contact (ou propose de le créer)."""
        partner = self.ensure_one()
        if not partner.wazo_user_id:
            raise UserError(
                'Aucun utilisateur Wazo pour %s. Utilisez le bouton '
                '« Créer utilisateur Wazo ».' % partner.name)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Utilisateur Wazo',
            'res_model': 'wazo.user',
            'res_id': partner.wazo_user_id.id,
            'view_mode': 'form',
        }

    def action_open_wazo_cdrs(self):
        """Ouvre le journal d'appels du contact."""
        partner = self.ensure_one()
        return self.env['wazo.cdr'].action_open_partner_cdrs(partner)
