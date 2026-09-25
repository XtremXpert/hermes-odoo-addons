# Part of the voipms_sms Odoo module. See LICENSE for details.
"""Boîte d'envoi SMS via VoIP.ms."""

from odoo.exceptions import UserError

from odoo import fields
from odoo import models

from ..services.sms_segmentation import normalize_nanp
from ..services.sms_segmentation import split_sms
from ..services.voipms_client import VoIPMSAPIError
from ..services.voipms_client import VoIPMSClient


class VoIPMSSmsOut(models.Model):
    _name = 'voipms.sms.out'
    _description = 'VoIP.ms : SMS envoyé'
    _order = 'date_sent desc, id desc'

    did_id = fields.Many2one('voipms.did', string='DID (émetteur)',
                             required=True, ondelete='restrict')
    destination = fields.Char(string='Destinataire', required=True)
    body = fields.Text(string='Message', required=True)
    state = fields.Selection(
        [('draft', 'Brouillon'), ('sent', 'Envoyé'), ('failed', 'Échec')],
        string='État', default='draft', index=True,
    )
    provider_message_ids = fields.Char(
        string='ID(s) message(s) VoIP.ms', readonly=True)
    error_message = fields.Char(string='Erreur', readonly=True)
    date_sent = fields.Datetime(string='Envoyé le', readonly=True)
    active = fields.Boolean(string='Actif', default=True)

    def action_send(self):
        """Envoie le message (segmenté si nécessaire) via VoIP.ms."""
        for msg in self:
            msg._validate_before_send()
            client = VoIPMSClient(self.env)
            try:
                provider_ids = []
                for segment in split_sms(msg.body):
                    response = client._request('sendSMS', {
                        'did': msg.did_id.number,
                        'dst': normalize_nanp(msg.destination),
                        'message': segment,
                    })
                    if response.get('message_id') is not None:
                        provider_ids.append(str(response['message_id']))
                msg.write({
                    'state': 'sent',
                    'provider_message_ids': ', '.join(provider_ids),
                    'error_message': False,
                    'date_sent': fields.Datetime.now(),
                })
            except VoIPMSAPIError as error:
                # L'échec API est consigné sur la ligne (état 'Échec' +
                # message d'erreur visible dans la vue liste) plutôt que de
                # remonter l'exception : la boîte d'envoi est l'historique des
                # tentatives, et le rollback transactionnel effacerait sinon
                # l'état 'failed'. L'utilisateur peut corriger et réessayer.
                msg.write({
                    'state': 'failed',
                    'error_message': str(error),
                })

    def _validate_before_send(self):
        self.ensure_one()
        if not (self.body or '').strip():
            raise UserError('Le message est vide.')
        try:
            normalize_nanp(self.destination)
        except ValueError:
            raise UserError(
                'Destinataire invalide (format NANP attendu) : %s'
                % self.destination) from None
        if not self.did_id.sms_enabled:
            raise UserError(
                'Le DID %s n\'a pas le SMS activé.' % self.did_id.number)
