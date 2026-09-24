# Part of the mailcow_admin Odoo module. See LICENSE for details.
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..services.mailcow_client import MailcowClient


class TestMailcowAliasFourreToutSynchronise(TransactionCase):
    """Un fourre-tout importé doit RESTER marqué « synchronisé ».

    Son nom d'alias est vide, et Odoo range alors False dans la colonne :
    comparer False à la chaîne vide faisait marquer la fiche comme absente du
    serveur juste après l'avoir importée, ce qui affichait un ruban rouge et
    proposait de la recréer.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain = cls.env['mailcow.domain'].search(
            [('name', '=', 'dc.com')], limit=1)
        if not cls.domain:
            cls.domain = cls.env['mailcow.domain'].create({'name': 'dc.com'})

    def test_fourre_tout_reste_synchronise(self):
        remote = {'data': [
            {'address': '@dc.com', 'domain': 'dc.com', 'goto': ['info@dc.com'],
             'active': '1', 'description': '', 'is_catch_all': 1, 'id': 7},
        ]}
        with patch.object(MailcowClient, '_request', return_value=remote):
            self.env['mailcow.alias'].action_sync_all_from_mailcow()

        fourre_tout = self.env['mailcow.alias'].search([
            ('domain_id', '=', self.domain.id), ('is_catch_all', '=', True)])
        self.assertTrue(fourre_tout)
        self.assertTrue(fourre_tout.synced,
                        "le fourre-tout est bien présent sur le serveur")
        self.assertEqual(fourre_tout.mailcow_id, '7')
