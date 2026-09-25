# Part of the mailcow_admin Odoo module. See LICENSE for details.
"""Tests des actions push/pull sur mailcow.domain."""

from unittest.mock import patch

from odoo.addons.mailcow_admin.services.mailcow_client import MailcowClient
from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged('mailcow_admin', 'post_install', '-at_install')
class TestMailcowDomain(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_str(
            'mailcow.base_url', 'https://mail.example.com')
        cls.env['ir.config_parameter'].sudo().set_str(
            'mailcow.api_key', 'test-api-key')

    def test_create_on_mailcow_sends_domain_and_marks_synced(self):
        domain = self.env['mailcow.domain'].create({
            'name': 'dc.com',
            'description': 'Mon domaine',
            'quota_mb': 100,
        })
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'domain_added', 'type': 'success'}],
        ) as request:
            domain.action_create_on_mailcow()
        # La creation et l'edition ne parlent pas le meme vocabulaire.
        # /add/domain attend defquota, maxquota et quota en MIO ; c'est ce que
        # montre l'exemple de l'API (« defquota: 3072 », « maxquota: 10240 »),
        # qui est aussi l'origine des valeurs par defaut du serveur.
        # Lui envoyer les noms de l'edition (def_quota_for_mbox, en octets) ne
        # produit ni erreur ni quota : Mailcow ignore ce qu'il ne connait pas
        # et repond « success ».
        request.assert_called_once_with('POST', '/add/domain', {
            'domain': 'dc.com',
            'description': 'Mon domaine',
            'active': '1',
            'defquota': 100,
            'maxquota': 100,
            'quota': 100,
        })
        self.assertTrue(domain.synced)

    def test_update_on_mailcow_sends_edit_payload(self):
        domain = self.env['mailcow.domain'].create(
            {'name': 'dc.com', 'synced': True})
        domain.description = 'Description mise à jour'
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'domain_updated', 'type': 'success'}],
        ) as request:
            domain.action_update_on_mailcow()
        # quota_mb = 0 : aucun quota n'est envoyé, pour ne pas écraser la
        # politique de quotas du serveur.
        # Mailcow attend {"items": [...], "attr": {...}} : un corps plat est
        # accepté puis ignoré, sans la moindre erreur.
        request.assert_called_once_with('POST', '/edit/domain', {
            'items': ['dc.com'],
            'attr': {
                'description': 'Description mise à jour',
                'active': '1',
            },
        })

    def test_update_on_mailcow_envoie_le_quota_en_mio(self):
        """Un quota non nul doit partir en Mio, sous les noms de l'ecriture.

        Mesure faite sur le serveur : /edit/domain accepte les cles
        « def_quota_for_mbox » et « max_quota_for_domain » en les recopiant
        dans son journal, repond « success », et n'applique rien. Ce sont les
        noms de la RELECTURE. L'ecriture attend « defquota », « maxquota » et
        « quota », en Mio.
        """
        domain = self.env['mailcow.domain'].create({
            'name': 'dc.com', 'synced': True, 'quota_mb': 200,
        })
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'domain_modified', 'type': 'success'}],
        ) as request:
            domain.action_update_on_mailcow()
        _, route, charge = request.call_args[0]
        self.assertEqual(route, '/edit/domain')
        attr = charge['attr']
        self.assertEqual(attr.get('defquota'), 200)
        self.assertEqual(attr.get('maxquota'), 200)
        self.assertEqual(attr.get('quota'), 200)
        self.assertNotIn('def_quota_for_mbox', attr)
        self.assertNotIn('max_quota_for_domain', attr)

    def test_delete_on_mailcow_unsyncs_and_archives(self):
        domain = self.env['mailcow.domain'].create(
            {'name': 'dc.com', 'synced': True})
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'domain_deleted', 'type': 'success'}],
        ) as request:
            domain.action_delete_on_mailcow()
        request.assert_called_once_with('POST', '/delete/domain', {'domain': 'dc.com'})
        self.assertFalse(domain.synced)
        self.assertFalse(domain.active)
        self.assertFalse(domain.mailboxes.synced)
        self.assertFalse(domain.aliases.synced)

    def test_sync_from_mailcow_creates_updates_and_unsyncs_local_only(self):
        local_only = self.env['mailcow.domain'].create(
            {'name': 'local-only.com', 'synced': True})
        existing = self.env['mailcow.domain'].create({
            'name': 'dc.com',
            'description': 'ancienne',
            'quota_mb': 50,
        })
        # Forme réelle de /get/domain/all : le nom du domaine est dans
        # « domain_name », et non « domain » (relevé sur le serveur).
        remote = {'data': [
            {
                'domain_name': 'dc.com',
                'description': 'nouvelle',
                'active': '1',
                'def_quota_for_mbox': 209715200,
            },
            {
                'id': 'def',
                'domain_name': 'new.com',
                'description': 'neuf',
                'active': '1',
                'def_quota_for_mbox': 0,
            },
        ]}
        with patch.object(MailcowClient, '_request', return_value=remote) as request:
            existing.action_sync_from_mailcow()
        request.assert_called_once_with('GET', '/get/domain/all', None)

        existing = self.env['mailcow.domain'].search([('name', '=', 'dc.com')])
        self.assertEqual(existing.description, 'nouvelle')
        self.assertEqual(existing.quota_mb, 200)
        self.assertTrue(existing.synced)

        new_domain = self.env['mailcow.domain'].search([('name', '=', 'new.com')])
        self.assertTrue(new_domain)
        self.assertTrue(new_domain.synced)

        local_only = local_only.search([('name', '=', 'local-only.com')])
        self.assertFalse(local_only.synced)

    def test_sync_revive_une_fiche_archivee_au_lieu_de_planter(self):
        """Une fiche archivee qui reapparait sur le serveur doit revivre.

        Le cas reel, rencontre en test sur un vrai domaine : on supprime un
        domaine — l'action archive la fiche locale — puis le domaine
        reapparait cote Mailcow. La synchronisation ne regardait que les
        fiches actives, concluait qu'il manquait, et tentait d'en creer une
        seconde : la contrainte d'unicite sur le nom faisait echouer toute la
        synchronisation au lieu de simplement raviver la fiche.
        """
        fiche = self.env['mailcow.domain'].create({'name': 'revient.com'})
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'domain_deleted', 'type': 'success'}],
        ):
            fiche.action_delete_on_mailcow()
        self.assertFalse(fiche.active, "l'action de suppression doit archiver")

        remote = {'data': [{
            'domain_name': 'revient.com',
            'description': 'de retour',
            'active': '1',
            'def_quota_for_mbox': 0,
        }]}
        with patch.object(MailcowClient, '_request', return_value=remote):
            self.env['mailcow.domain'].action_sync_all_from_mailcow()

        retrouvees = self.env['mailcow.domain'].with_context(active_test=False).search(
            [('name', '=', 'revient.com')])
        self.assertEqual(len(retrouvees), 1, "une seconde fiche a ete tentee")
        self.assertTrue(retrouvees.active, "la fiche archivee n'a pas ete ravivee")
        self.assertTrue(retrouvees.synced)
        self.assertEqual(retrouvees.description, 'de retour')

    def test_sync_all_works_without_any_local_record(self):
        """Amorcer une base vide : aucune fiche locale n'est nécessaire."""
        remote = {'data': [
            {'domain_name': 'dc.com', 'description': 'importé', 'active': '1'},
            {'domain_name': 'autre.com', 'description': '', 'active': '1'},
        ]}
        with patch.object(MailcowClient, '_request', return_value=remote):
            self.env['mailcow.domain'].action_sync_all_from_mailcow()
        self.assertEqual(
            sorted(self.env['mailcow.domain'].search(
                [('name', 'in', ['dc.com', 'autre.com'])]).mapped('name')),
            ['autre.com', 'dc.com'])
        self.assertTrue(self.env['mailcow.domain'].search(
            [('name', 'in', ['dc.com', 'autre.com'])]).mapped('synced'))
