# L'aperçu : décrire ce qu'une synchronisation changerait, sans rien écrire.
#
# Les listes simulées ne contiennent que les fiches du test : les fiches réelles
# de la base de développement y apparaissent donc comme disparues, ce qui est
# exact et sans importance ici — chaque assertion vise sa propre fiche.
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..services.mailcow_client import MailcowClient


class TestApercu(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain = cls.env['mailcow.domain'].search(
            [('name', '=', 'dc.com')], limit=1)
        if not cls.domain:
            cls.domain = cls.env['mailcow.domain'].create({'name': 'dc.com'})

    def _entree(self, local, nom='', domaine='dc.com', quota=0):
        return {'local_part': local, 'domain': domaine, 'active': 1,
                'name': nom, 'description': '', 'quota': quota}

    def test_l_apercu_ne_change_rien_et_n_ecrit_pas_au_serveur(self):
        existante = self.env['mailcow.mailbox'].create({
            'local_part': 'existante', 'domain_id': self.domain.id,
            'name': 'avant', 'synced': True,
        })
        with patch.object(MailcowClient, '_request',
                          return_value=[self._entree('existante', nom='après')]) as appel:
            self.env['mailcow.mailbox']._sync_all_from_mailcow(dry_run=True)
        existante.invalidate_recordset()
        self.assertEqual(existante.name, 'avant', "l'aperçu a écrit")
        self.assertTrue(all(a[0][0] == 'GET' for a in appel.call_args_list),
                        "l'aperçu a écrit sur le serveur")

    def test_l_apercu_nomme_les_fiches_et_les_champs(self):
        connue = self.env['mailcow.mailbox'].create({
            'local_part': 'connue', 'domain_id': self.domain.id,
            'name': 'avant', 'synced': True,
        })
        disparue = self.env['mailcow.mailbox'].create({
            'local_part': 'absente', 'domain_id': self.domain.id, 'synced': True,
        })
        with patch.object(MailcowClient, '_request',
                          return_value=[self._entree('connue', nom='après'),
                                        self._entree('nouvelle')]):
            plan = self.env['mailcow.mailbox']._sync_all_from_mailcow(dry_run=True)
        texte = '\n'.join(plan)
        self.assertIn('connue@dc.com', texte, 'la mise à jour est mal nommée')
        self.assertIn('name', texte, 'le champ qui changerait n est pas nommé')
        self.assertIn('nouvelle@dc.com', texte, 'la création n est pas annoncée')
        self.assertIn('absente@dc.com', texte, 'la disparition n est pas annoncée')
        connue.invalidate_recordset()
        disparue.invalidate_recordset()
        self.assertEqual(connue.name, 'avant')
        self.assertTrue(disparue.synced, 'une fiche a été marquée disparue')

    def test_un_serveur_identique_n_annonce_rien_pour_cette_fiche(self):
        calme = self.env['mailcow.mailbox'].create({
            'local_part': 'calme', 'domain_id': self.domain.id,
            'name': 'pareil', 'synced': True})
        with patch.object(MailcowClient, '_request',
                          return_value=[self._entree('calme', nom='pareil')]):
            plan = self.env['mailcow.mailbox']._sync_all_from_mailcow(dry_run=True)
        self.assertNotIn('calme@dc.com', '\n'.join(plan),
                         'une fiche identique est annoncée comme changeante')

    def test_le_bouton_ouvre_un_apercu(self):
        with patch.object(MailcowClient, '_request',
                          return_value=[self._entree('nimporte')]):
            action = self.env['mailcow.mailbox'].action_preview_sync_from_mailcow()
        self.assertEqual(action['res_model'], 'mailcow.sync.preview')
        apercu = self.env['mailcow.sync.preview'].browse(action['res_id'])
        self.assertTrue(apercu.plan)
