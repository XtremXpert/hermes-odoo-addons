# Part of the mailcow_admin Odoo module. See LICENSE for details.
from odoo import fields, models

from ..services.mailcow_client import MailcowClient


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mailcow_base_url = fields.Char(
        string='URL du serveur Mailcow',
        config_parameter='mailcow.base_url',
        help="URL de base du serveur Mailcow, sans /api/v1 "
             "(ex. https://mail.diverse-cite.com).",
    )
    mailcow_api_key = fields.Char(
        string='Clé API Mailcow',
        config_parameter='mailcow.api_key',
        help="Clé API créée dans l'interface d'administration de Mailcow "
             "(section API, en bas de l'écran d'accueil).",
    )

    def action_test_mailcow_connection(self):
        """Teste la connexion en listant les domaines du serveur."""
        client = MailcowClient(self.env)
        response = client._request('GET', '/get/domain/111')
        entries = response.get('data') if isinstance(response, dict) else response
        count = len([e for e in entries if isinstance(e, dict)])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Mailcow',
                'message': (
                    'Connexion à Mailcow réussie : %d domaine(s) trouvé(s).'
                    % count
                ),
                'type': 'success',
                'sticky': False,
            },
        }