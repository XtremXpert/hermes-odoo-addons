# Part of the mailcow_admin Odoo module. See LICENSE for details.
"""Tests des actions push/pull sur mailcow.domain."""

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
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

    def test_sync_lit_les_plafonds_et_l_occupation(self):
        """Le domaine doit rapporter combien de boites il porte, et sa limite.

        Sans ces quatre valeurs, impossible d'afficher « 8 sur 10 » : le
        modele ne les relisait pas, et une limite atteinte ne se voyait nulle
        part avant que la creation echoue cote serveur.
        """
        remote = {'data': [{
            'domain_name': 'dc.com',
            'description': '',
            'active': '1',
            'def_quota_for_mbox': 0,
            'mboxes_in_domain': 8,
            'max_num_mboxes_for_domain': 10,
            'aliases_in_domain': 3,
            'max_num_aliases_for_domain': 400,
        }]}
        with patch.object(MailcowClient, '_request', return_value=remote):
            self.env['mailcow.domain'].action_sync_all_from_mailcow()
        domaine = self.env['mailcow.domain'].search([('name', '=', 'dc.com')])
        self.assertEqual(domaine.mailboxes_used, 8)
        self.assertEqual(domaine.mailboxes_max, 10)
        self.assertEqual(domaine.aliases_used, 3)
        self.assertEqual(domaine.aliases_max, 400)

    def test_les_plafonds_partent_en_nombre_entier(self):
        """Les plafonds s'ecrivent en nombre, pas en Mio ni en octets.

        /add/domain et /edit/domain attendent « mailboxes » et « aliases »
        (l'exemple de l'API donne 10 et 400). Un plafond local a 0 ne doit
        rien envoyer : c'est « la valeur du serveur », pas « zero ».
        """
        domaine = self.env['mailcow.domain'].create({
            'name': 'dc.com', 'description': 'x', 'quota_mb': 100,
            'mailboxes_max': 25, 'aliases_max': 200,
        })
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'domain_added', 'type': 'success'}],
        ) as request:
            domaine.action_create_on_mailcow()
        _, route, charge = request.call_args[0]
        self.assertEqual(route, '/add/domain')
        self.assertEqual(charge['mailboxes'], 25)
        self.assertEqual(charge['aliases'], 200)

        # Un domaine sans plafond n'en envoie aucun.
        sans = self.env['mailcow.domain'].create({'name': 'sans.com'})
        with patch.object(
            MailcowClient, '_request',
            return_value=[{'msg': 'domain_added', 'type': 'success'}],
        ) as request2:
            sans.action_create_on_mailcow()
        _, _, charge2 = request2.call_args[0]
        self.assertNotIn('mailboxes', charge2)
        self.assertNotIn('aliases', charge2)

    def test_le_tableau_de_bord_agrege_les_domaines(self):
        """Le calcul est fait cote serveur, pas dans le navigateur.

        Une seule source de verite : compter les boites et jauger les quotas
        en Python evite de refaire le calcul en JavaScript, ou il divergerait
        au premier changement de regle.
        """
        # « boites » compte desormais les fiches, il ne somme plus l'occupation
        # des domaines : on releve avant, et on ne mesure que l'ecart. Un compte
        # absolu passerait sur la base de developpement et casserait sur une
        # base neuve, comme en integration continue.
        boites_avant = self.env['mailcow.domain'].donnees_tableau_de_bord()['totaux']['boites']

        d1 = self.env['mailcow.domain'].create({
            'name': 'un.com', 'active': True, 'synced': True,
            'mailboxes_used': 8, 'mailboxes_max': 10,
            'aliases_used': 3, 'aliases_max': 400,
        })
        self.env['mailcow.domain'].create({
            'name': 'deux.com', 'active': True, 'synced': True,
            'mailboxes_used': 1, 'mailboxes_max': 10,
        })
        self.env['mailcow.mailbox'].create({
            'local_part': 'presque-plein', 'domain_id': d1.id,
            'quota_mb': 100, 'quota_used_mb': 95, 'active': True,
        })
        donnees = self.env['mailcow.domain'].donnees_tableau_de_bord()

        # Les tests tournent sur la base reelle : viser les fiches creees ici,
        # jamais un compte absolu, qui dependrait du decor.
        noms = [ligne['nom'] for ligne in donnees['domaines']]
        self.assertIn('un.com', noms)
        self.assertIn('deux.com', noms)
        un = [ligne for ligne in donnees['domaines'] if ligne['nom'] == 'un.com'][0]
        self.assertEqual(un['boites_utilisees'], 8)
        self.assertEqual(un['boites_max'], 10)
        self.assertAlmostEqual(un['occupation'], 80.0)
        self.assertFalse(un['dkim'])
        self.assertGreaterEqual(donnees['totaux']['domaines'], 2)
        self.assertEqual(donnees['totaux']['boites'], boites_avant + 1)
        # La pression des quotas est desormais une alerte, avec son modele et
        # son filtre : c'est elle qui rend le chiffre actionnable.
        par_cle = {alerte['cle']: alerte for alerte in donnees['alertes']}
        self.assertEqual(par_cle['boites_serrees']['nombre'], 1)
        self.assertEqual(par_cle['boites_serrees']['modele'], 'mailcow.mailbox')
        self.assertEqual(par_cle['boites_serrees']['filtre'][0][0], 'id')

    def test_le_tableau_de_bord_donne_de_quoi_interagir(self):
        """Ouvrir, trier, chercher : il faut de quoi designer chaque fiche.

        Les listes portent l'identifiant de la fiche locale, pour qu'un clic
        ouvre la bonne. Sans lui, l'interface n'aurait que le nom pour la
        retrouver — ce qui casse des qu'un nom change.
        """
        domaine = self.env['mailcow.domain'].create({
            'name': 'interaction.com', 'quota_mb': 100, 'synced': True,
            'mailboxes_max': 5, 'aliases_max': 5,
        })
        boite = self.env['mailcow.mailbox'].create({
            'local_part': 'clic', 'domain_id': domaine.id, 'quota_mb': 100,
            'quota_used_mb': 12.5, 'messages': 7, 'active': True, 'synced': True,
        })
        alias = self.env['mailcow.alias'].create({
            'alias_name': 'renvoi', 'domain_id': domaine.id, 'synced': True,
        })

        donnees = self.env['mailcow.domain'].donnees_tableau_de_bord()
        boites = {b['id']: b for b in donnees['boites']}
        alias_par_id = {a['id']: a for a in donnees['alias']}

        self.assertIn(boite.id, boites)
        self.assertEqual(boites[boite.id]['nom'], 'clic@interaction.com')
        self.assertEqual(boites[boite.id]['domaine'], 'interaction.com')
        self.assertEqual(boites[boite.id]['messages'], 7)
        self.assertAlmostEqual(boites[boite.id]['pourcentage'], 12.5)
        self.assertIn(alias.id, alias_par_id)
        self.assertEqual(alias_par_id[alias.id]['nom'], 'renvoi@interaction.com')
        self.assertFalse(alias_par_id[alias.id]['catch_all'])
        # L'adresse de l'interface Mailcow, pour y renvoyer d'un clic.
        self.assertIn('mailcow_url', donnees)

    def test_le_tableau_de_bord_signale_ce_qui_cloche(self):
        """Un tableau de bord sert a voir ce qui ne va pas, pas a compter.

        Chaque alerte porte le modele a ouvrir et le filtre a appliquer : le
        composant se contente de suivre, et la regle vit au meme endroit que
        les autres regles du module.
        """
        # Les tests tournent sur la base reelle : on releve l etat avant, et on
        # ne mesure que l ecart. Un compte absolu dependrait du decor.
        avant = {
            a['cle']: a['nombre']
            for a in self.env['mailcow.domain'].donnees_tableau_de_bord()['alertes']
        }

        domaine = self.env['mailcow.domain'].create({
            'name': 'alerte.com', 'description': 'x', 'quota_mb': 100,
            'mailboxes_max': 10, 'aliases_max': 10,
            'dkim_record': 'v=DKIM1; k=rsa; p=abc',
        })
        # Une boite desactivee.
        self.env['mailcow.mailbox'].create({
            'local_part': 'desactivee', 'domain_id': domaine.id,
            'quota_mb': 100, 'active': False, 'synced': True,
        })
        # Une boite ouverte mais sans usage depuis plus d'un an, sans TLS impose.
        self.env['mailcow.mailbox'].create({
            'local_part': 'dormante', 'domain_id': domaine.id,
            'quota_mb': 100, 'active': True, 'synced': True,
            'tls_enforce_in': False,
            'last_smtp_login': fields.Datetime.now() - timedelta(days=400),
        })
        # Un alias sans destination, et un attrape-tout.
        # « alias_name » ne porte que la partie locale, et un fourre-tout a
        # un nom vide : le module le refuse autrement, a raison.
        self.env['mailcow.alias'].create({
            'alias_name': 'perdu', 'domain_id': domaine.id, 'synced': True,
        })
        self.env['mailcow.alias'].create({
            'alias_name': '', 'domain_id': domaine.id,
            'is_catch_all': True, 'synced': True,
        })

        donnees = self.env['mailcow.domain'].donnees_tableau_de_bord()
        apres = {a['cle']: a['nombre'] for a in donnees['alertes']}

        # Chaque fiche creee ici doit faire bouger exactement une alerte.
        self.assertEqual(apres['boites_desactivees'], avant['boites_desactivees'] + 1)
        self.assertEqual(apres['boites_dormantes'], avant['boites_dormantes'] + 1)
        self.assertEqual(apres['tls_non_impose'], avant['tls_non_impose'] + 1)
        self.assertEqual(apres['alias_sans_destination'],
                         avant['alias_sans_destination'] + 1)
        self.assertEqual(apres['catch_all'], avant['catch_all'] + 1)

        # Chaque alerte doit etre actionnable : un modele et un filtre.
        for alerte in donnees['alertes']:
            self.assertTrue(alerte['modele'], alerte['cle'])
            self.assertIsInstance(alerte['filtre'], list, alerte['cle'])

        # Une boite sans quota ne peut pas afficher un taux : « 0 % » se lirait
        # « vide » alors qu'elle est sans limite. Rien, plutot qu'un faux zero.
        sans_plafond = self.env['mailcow.mailbox'].create({
            'local_part': 'sans-plafond', 'domain_id': domaine.id,
            'quota_mb': 0, 'quota_used_mb': 500.0, 'active': True, 'synced': True,
        })
        # Une boite qui n'a jamais servi est la plus dormante de toutes : elle
        # doit figurer dans la liste, et non seulement dans le compte.
        jamais = self.env['mailcow.mailbox'].create({
            'local_part': 'jamais-connectee', 'domain_id': domaine.id,
            'quota_mb': 100, 'active': True, 'synced': True,
        })
        seconde = self.env['mailcow.domain'].donnees_tableau_de_bord()
        ligne = [b for b in seconde['grosses_boites'] if b['id'] == sans_plafond.id]
        self.assertTrue(ligne, "la boite sans quota doit figurer dans les gourmandes")
        self.assertIsNone(ligne[0]['pourcentage'])
        self.assertIn(jamais.id, [b['id'] for b in seconde['dormantes']],
                      "une boite jamais utilisee doit figurer dans les dormantes")

        # Les totaux enrichis.
        self.assertGreaterEqual(donnees['totaux']['boites'], 2)
        self.assertGreaterEqual(donnees['totaux']['alias'], 2)
        self.assertIn('messages', donnees['totaux'])
        self.assertIn('quota_alloue_mb', donnees['totaux'])
        self.assertIn('grosses_boites', donnees)

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
