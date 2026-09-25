# Les fiches disparues du serveur : celles qu'on croyait présentes et que
# Mailcow ne liste plus. À ne pas confondre avec celles jamais poussées.
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..services.mailcow_client import MailcowClient

DOMAINE_DES_DISPARUES = [
    ('synced', '=', False),
    ('last_synced_on', '!=', False),
    ('active', '=', True),
]


class TestDisparues(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain = cls.env['mailcow.domain'].search(
            [('name', '=', 'dc.com')], limit=1)
        if not cls.domain:
            cls.domain = cls.env['mailcow.domain'].create({'name': 'dc.com'})

    def _boite(self, local, synced=True, actif=True):
        return self.env['mailcow.mailbox'].create({
            'local_part': local, 'domain_id': self.domain.id,
            'synced': synced, 'active': actif,
        })

    def test_la_synchronisation_note_la_date(self):
        entree = {'local_part': 'vue', 'domain': 'dc.com', 'active': 1,
                  'quota': 0, 'name': '', 'description': ''}
        with patch.object(MailcowClient, '_request', return_value=[entree]):
            self.env['mailcow.mailbox'].action_sync_all_from_mailcow()
        boite = self.env['mailcow.mailbox'].search(
            [('local_part', '=', 'vue'), ('domain_id', '=', self.domain.id)], limit=1)
        self.assertTrue(boite.last_synced_on)

    def test_une_fiche_jamais_poussee_n_est_pas_une_disparue(self):
        """La distinction qui compte : jamais vue n'est pas disparue."""
        jamais = self._boite('jamais', synced=False)
        self.assertFalse(jamais.last_synced_on)
        self.assertNotIn(jamais, self.env['mailcow.mailbox'].search(DOMAINE_DES_DISPARUES))

    def test_une_fiche_disparue_est_reconnue(self):
        disparue = self._boite('disparue', synced=False)
        disparue.last_synced_on = '2026-09-01 10:00:00'
        self.assertIn(disparue, self.env['mailcow.mailbox'].search(DOMAINE_DES_DISPARUES))

    def test_oublier_archive_sans_toucher_au_serveur(self):
        boite = self._boite('oubliee')
        with patch.object(MailcowClient, '_request') as appel:
            boite.action_forget_locally()
        self.assertFalse(boite.active)
        appel.assert_not_called()

    def test_purger_supprime_definitivement(self):
        boite = self._boite('purgee')
        with patch.object(MailcowClient, '_request') as appel:
            boite.action_purge_local()
        self.assertFalse(self.env['mailcow.mailbox'].search(
            [('local_part', '=', 'purgee'), ('domain_id', '=', self.domain.id)]))
        appel.assert_not_called()
