# Part of the asterisk_ari Odoo module. See LICENSE for details.
"""Historique des appels click-to-call (origination ARI)."""

from odoo import fields
from odoo import models
from odoo.exceptions import UserError

from ..services.ari_client import ARI
from ..services.ari_client import ARIConfigError
from ..services.ari_client import ARIError


class AsteriskCall(models.Model):
    _name = 'asterisk.call'
    _description = 'Appel (click-to-call)'
    _order = 'date_started desc, id desc'

    partner_id = fields.Many2one(
        'res.partner', string='Contact', ondelete='set null')
    phone = fields.Char(string='Numéro appelé', required=True)
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('ringing', 'Sonnerie'),
        ('answered', 'Répondu'),
        ('ended', 'Terminé'),
        ('failed', 'Échec'),
    ], string='État', default='draft', index=True)
    ari_call_id = fields.Char(string='ID appel ARI', readonly=True)
    error_message = fields.Char(string='Erreur', readonly=True)
    date_started = fields.Datetime(string='Démarré le', readonly=True)
    date_ended = fields.Datetime(string='Terminé le', readonly=True)
    active = fields.Boolean(string='Actif', default=True)

    def action_originate(self):
        """Démarre l'appel (ARI ``POST /calls``) vers ``phone``."""
        self.ensure_one()
        if not (self.phone or '').strip():
            raise UserError('Le numéro appelé est vide.')
        client = ARI(self.env)
        caller_id = self.env.company.phone or ''
        try:
            result = client.originate(
                'PJSIP/%s' % self.phone.strip(),
                app='odoo_click',
                app_answered=False,
                caller_id=caller_id or None,
            )
        except (ARIError, ARIConfigError) as error:
            # Comme pour voipms_sms : consigner l'échec sur la ligne plutôt
            # que de relancer (le rollback effacerait sinon l'état 'failed').
            self.write({
                'state': 'failed',
                'error_message': str(error),
            })
            return
        self.write({
            'state': 'ringing',
            'ari_call_id': (
                result.get('id') if isinstance(result, dict) else ''),
            'date_started': fields.Datetime.now(),
            'error_message': False,
        })

    def action_hangup(self):
        """Raccroche l'appel (ARI ``DELETE /calls/{id}``)."""
        self.ensure_one()
        if not self.ari_call_id:
            raise UserError("Aucun appel ARI actif sur cette ligne.")
        client = ARI(self.env)
        try:  # noqa: SIM105 - meilleur effort : le commentaire dit pourquoi on se tait
            client.hangup(self.ari_call_id)
        except ARIError:
            # Meilleur effort : l'appel a peut-être déjà fini côté PBX.
            pass
        self.write({
            'state': 'ended',
            'date_ended': fields.Datetime.now(),
        })
