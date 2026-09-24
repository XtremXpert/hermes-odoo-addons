# La forme réelle des routes d'édition de Mailcow : {"items": [...], "attr": {...}}.
#
# Un corps plat est accepté, la réponse dit « Task completed », et RIEN n'est
# modifié. Ces tests verrouillent la forme qui a un effet, mesurée en direct
# sur le serveur : items = l'identité de l'objet, attr = les attributs changés.
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..services.mailcow_client import MailcowClient

REPONSE = [{'msg': 'Task completed', 'type': 'success'}]


class TestFormeDesEditions(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain = cls.env['mailcow.domain'].search(
            [('name', '=', 'dc.com')], limit=1)
        if not cls.domain:
            cls.domain = cls.env['mailcow.domain'].create({'name': 'dc.com'})

    def test_mise_a_jour_du_domaine(self):
        domaine = self.env['mailcow.domain'].create(
            {'name': 'forme.com', 'synced': True})
        domaine.description = 'modifiee'
        with patch.object(MailcowClient, '_request',
                          return_value=REPONSE) as requete:
            domaine.action_update_on_mailcow()
        requete.assert_called_once_with('POST', '/edit/domain', {
            'items': ['forme.com'],
            'attr': {'description': 'modifiee', 'active': '1'},
        })

    def test_mise_a_jour_d_une_boite(self):
        boite = self.env['mailcow.mailbox'].create({
            'local_part': 'forme', 'domain_id': self.domain.id,
            'quota_mb': 42, 'synced': True,
        })
        with patch.object(MailcowClient, '_request',
                          return_value=REPONSE) as requete:
            boite.action_update_on_mailcow()
        appels = [a for a in requete.call_args_list if a[0][0] == 'POST']
        self.assertEqual(len(appels), 1)
        self.assertEqual(appels[0][0][1], '/edit/mailbox')
        charge = appels[0][0][2]
        self.assertEqual(charge['items'], ['forme@dc.com'])
        self.assertEqual(charge['attr']['quota'], 42)
        # L'identité ne se répète pas dans « attr ».
        self.assertNotIn('local_part', charge['attr'])
        self.assertNotIn('domain', charge['attr'])

    def test_mise_a_jour_d_un_alias(self):
        cible = self.env['mailcow.email_address'].create(
            {'address': 'cible@dc.com'})
        alias = self.env['mailcow.alias'].create({
            'domain_id': self.domain.id, 'alias_name': 'forme',
            'address_ids': [(6, 0, [cible.id])], 'synced': True,
        })
        alias.mailcow_id = '77'
        with patch.object(MailcowClient, '_request',
                          return_value=REPONSE) as requete:
            alias.action_update_on_mailcow()
        appels = [a for a in requete.call_args_list if a[0][0] == 'POST']
        self.assertEqual(len(appels), 1)
        self.assertEqual(appels[0][0][1], '/edit/alias')
        charge = appels[0][0][2]
        # Un alias s'identifie par son identifiant Mailcow, pas par son adresse.
        self.assertEqual(charge['items'], ['77'])
        self.assertEqual(charge['attr']['goto'], 'cible@dc.com')
