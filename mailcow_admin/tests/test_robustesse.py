# Deux protections : ne jamais conclure à la disparition totale sur un
# listage vide, et reprendre un appel que le serveur a refusé passagèrement.
import urllib.error
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..services.mailcow_client import MailcowAPIError
from ..services.mailcow_client import MailcowClient


class FausseReponse:
    """Le minimum qu'urllib attend d'une réponse."""

    def __init__(self, corps):
        self._corps = corps.encode('utf-8')

    def read(self):
        return self._corps

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestListageVide(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain = cls.env['mailcow.domain'].search(
            [('name', '=', 'dc.com')], limit=1)
        if not cls.domain:
            cls.domain = cls.env['mailcow.domain'].create({'name': 'dc.com', 'synced': True})

    def test_un_listage_vide_ne_marque_rien_comme_disparu(self):
        """Le cas qui compte : une panne passagère ne doit pas salir l'état."""
        boite = self.env['mailcow.mailbox'].create({
            'local_part': 'temoin', 'domain_id': self.domain.id, 'synced': True,
        })
        with patch.object(MailcowClient, '_request', return_value=[]):
            with self.assertRaises(MailcowAPIError):
                self.env['mailcow.mailbox'].action_sync_all_from_mailcow()
        self.assertTrue(boite.synced, "la fiche a été marquée disparue à tort")

    def test_un_serveur_vierge_se_synchronise_sans_erreur(self):
        """Sans aucune fiche locale, un listage vide est parfaitement normal."""
        self.env['mailcow.mailbox'].with_context(active_test=False).search([]).unlink()
        with patch.object(MailcowClient, '_request', return_value=[]):
            self.env['mailcow.mailbox'].action_sync_all_from_mailcow()


class TestQuotaEnTexte(TransactionCase):
    """Un quota qui arrive en texte ne doit pas faire lever la synchronisation."""

    def test_le_domaine_lit_un_quota_textuel(self):
        remote = {'data': [{'domain_name': 'texte.com', 'active': '1',
                            'def_quota_for_mbox': '209715200'}]}
        with patch.object(MailcowClient, '_request', return_value=remote):
            self.env['mailcow.domain'].action_sync_all_from_mailcow()
        domaine = self.env['mailcow.domain'].search([('name', '=', 'texte.com')], limit=1)
        self.assertEqual(domaine.quota_mb, 200)


class TestReprises(TransactionCase):

    def _client(self):
        return MailcowClient(self.env, base_url='https://exemple.test',
                             api_key='clef-de-test')

    def test_reprend_apres_un_refus_passager(self):
        refus = urllib.error.HTTPError(
            'https://exemple.test', 503, 'Service Unavailable', {}, None)
        with patch('urllib.request.urlopen',
                   side_effect=[refus, FausseReponse('[{"type": "success"}]')]) as appel:
            resultat = self._client()._request('GET', '/get/domain/all', None)
        self.assertEqual(resultat, [{'type': 'success'}])
        self.assertEqual(appel.call_count, 2, "le serveur n'a pas été réessayé")

    def test_ne_reprend_pas_sur_une_erreur_definitive(self):
        """Un 404 ne se répare pas en réessayant : on le dit tout de suite."""
        introuvable = urllib.error.HTTPError(
            'https://exemple.test', 404, 'Not Found', {}, None)
        with patch('urllib.request.urlopen', side_effect=introuvable) as appel:
            with self.assertRaises(MailcowAPIError):
                self._client()._request('GET', '/get/inconnu/all', None)
        self.assertEqual(appel.call_count, 1)
