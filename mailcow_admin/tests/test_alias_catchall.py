# Part of the mailcow_admin Odoo module. See LICENSE for details.
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..services.mailcow_client import MailcowClient


class TestMailcowAliasFourreToutSynchronise(TransactionCase):
    """Un fourre-tout importé doit RESTER marqué « synchronisé ».

    Un fourre-tout créé depuis le formulaire n'a pas de nom d'alias, et Odoo
    range alors False dans la colonne. Comparer False à la chaîne vide de la
    clé distante faisait marquer la fiche comme absente du serveur juste après
    l'avoir importée : ruban rouge, et bouton « Créer sur Mailcow » de retour.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain = cls.env['mailcow.domain'].search(
            [('name', '=', 'dc.com')], limit=1)
        if not cls.domain:
            cls.domain = cls.env['mailcow.domain'].create({'name': 'dc.com'})

    def test_fourre_tout_reste_synchronise(self):
        # Le fourre-tout existe déjà en local, nom d'alias non renseigné :
        # c'est la fiche que produit le formulaire.
        self.env['mailcow.alias'].create({
            'domain_id': self.domain.id,
            'is_catch_all': True,
        })
        remote = {'data': [
            {'address': '@dc.com', 'domain': 'dc.com', 'goto': ['info@dc.com'],
             'active': '1', 'description': '', 'is_catch_all': 1, 'id': 7},
        ]}
        with patch.object(MailcowClient, '_request', return_value=remote):
            self.env['mailcow.alias'].action_sync_all_from_mailcow()

        fourre_tout = self.env['mailcow.alias'].search([
            ('domain_id', '=', self.domain.id), ('is_catch_all', '=', True)],
            limit=1)
        self.assertTrue(fourre_tout)
        self.assertTrue(
            fourre_tout.synced,
            "le fourre-tout est bien présent sur le serveur : sa fiche ne doit "
            "pas retomber en « non synchronisé »")
        self.assertEqual(fourre_tout.mailcow_id, '7')
