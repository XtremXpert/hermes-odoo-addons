# Part of the wazo_server Odoo module. See LICENSE for details.
"""Tests de l'adoption des tenants déjà présents sur le PBX.

Le module ne savait que **créer** un tenant. Après une réinitialisation de sa
base — ou sur une instance neuve posée devant un Wazo déjà peuplé —, les
tenants vivants sont donc invisibles d'Odoo, et le menu « Serveur Wazo »
s'affiche vide sans que rien ne manque au PBX.

L'adoption est une **lecture** : rien n'est créé ni modifié côté PBX, et les
fiches déjà connues ne sont jamais touchées (un jeton vivant ne s'écrase pas).

Le faux serveur reproduit le comportement qui contraint la mise en œuvre : le
listage des tenants est **cloisonné par l'en-tête**, donc partir du tenant des
réglages ne montre que lui et ses enfants.
"""

from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.wazo_phone.services.wazo_client import WazoAPIError, WazoClient

from .test_tenant_provisioning import WazoServerTestBase

#: UUID **fictifs**, volontairement : la suite tourne sur la base de
#: développement, qui porte des tenants réels (adoptés depuis le PBX). Des
#: identifiants réels ici feraient collisionner les fiches créées par les tests
#: avec les fiches vivantes.
RACINE = 'aaaa1111-0000-0000-0000-00000000a001'
CLIENT = 'bbbb2222-0000-0000-0000-00000000a002'
#: Un second client, pour le cas des identifiants à nettoyer.
AUTRE = 'cccc3333-0000-0000-0000-00000000a003'


@tagged('post_install', '-at_install')
class TestTenantAdoption(WazoServerTestBase):
    """L'adoption vue depuis Odoo : ce qui entre en base, et ce qui n'y touche pas."""

    def setUp(self):
        super().setUp()
        # La base de développement porte des tenants réels : on vise une racine
        # fictive, pour que les fiches de ce test ne croisent jamais les vraies.
        self.env['ir.config_parameter'].sudo().set_str(
            'wazo.tenant_id', RACINE)

    def _faux_pbx(self, arbre):
        """Faux PBX dont le listage se comporte comme wazo-auth.

        Rend ``(appels, repondre)``. Chaque appel consigné est un quadruplet
        ``(service, méthode, chemin, tenant)`` — le tenant étant l'en-tête
        employé, ce qui permet de vérifier **avec quel tenant** on a listé.
        """
        appels = []

        def repondre(client, service, method, path, params=None, body=None,
                     basic=None):
            appels.append((service, method, path, client.tenant_id))
            if service == 'confd' and path == '/contexts' and method == 'GET':
                # Les contextes vivent côté confd, et se lisent avec **son**
                # en-tête. Wazo suffixe le nom demandé : « ctx-<slug>-internal »
                # n'est qu'une approximation, d'où le suffixe ci-dessous.
                fiche = next((tenant for tenant in arbre
                              if tenant['uuid'] == client.tenant_id), {})
                return {'total': 1, 'items': [{
                    'id': 7,
                    'name': 'ctx-%s-internal-%s' % (fiche.get('slug'),
                                                    client.tenant_id[:8])}]}
            if service != 'auth':
                return None
            if path == '/tenants' and method == 'GET':
                # Cloisonnement : le sous-arbre du tenant porté par l'en-tête.
                sous_arbre = [
                    tenant for tenant in arbre
                    if tenant['uuid'] == client.tenant_id
                    or tenant.get('parent_uuid') == client.tenant_id]
                return {'total': len(sous_arbre), 'items': sous_arbre}
            if path.startswith('/tenants/') and method == 'GET':
                identifiant = path.rsplit('/', 1)[-1]
                # Cloisonnement, dans les deux sens — mesuré en direct : un
                # tenant **hors** du sous-arbre de l'en-tête n'existe pas pour
                # cette requête. wazo-auth répond 404 « unknown-tenant », et
                # non une permission refusée. C'est ce qui interdit de lire un
                # parent avec l'en-tête de son enfant.
                dans_le_sous_arbre = {
                    tenant['uuid'] for tenant in arbre
                    if tenant['uuid'] == client.tenant_id
                    or tenant.get('parent_uuid') == client.tenant_id}
                if identifiant not in dans_le_sous_arbre:
                    raise WazoAPIError(
                        "Erreur de l'API Wazo (GET %s) : HTTP 404. "
                        '{"message": "No such tenant", "error_id": '
                        '"unknown-tenant"}' % path)
                for tenant in arbre:
                    if tenant['uuid'] == identifiant:
                        return tenant
                return {}
            return None

        return appels, repondre

    def _adopter(self, arbre):
        appels, repondre = self._faux_pbx(arbre)
        with patch.object(WazoClient, '_request', autospec=True,
                          side_effect=repondre):
            resultat = self.env['wazo.server.tenant'].action_adopt_from_wazo()
        return appels, resultat

    # ------------------------------------------------------------------
    # Ce qui entre en base
    # ------------------------------------------------------------------

    def test_adoption_creates_the_missing_tenants(self):
        """Un tenant vivant au PBX et inconnu d'Odoo entre dans la base."""
        arbre = [
            {'uuid': RACINE, 'name': 'master', 'slug': 'master',
             'parent_uuid': RACINE},
            {'uuid': CLIENT, 'name': 'Client Alpha', 'slug': 'alpha',
             'parent_uuid': RACINE},
        ]
        self._adopter(arbre)
        fiches = self.env['wazo.server.tenant'].search(
            [('remote_uuid', 'in', (RACINE, CLIENT))])
        self.assertEqual(sorted(fiches.mapped('remote_uuid')), [RACINE, CLIENT])
        self.assertEqual(sorted(fiches.mapped('name')), ['Client Alpha', 'master'])
        for fiche in fiches:
            self.assertEqual(
                fiche.state, 'created',
                "un tenant adopté existe bel et bien : son état doit le dire.")

    def test_adoption_writes_nothing_on_the_pbx(self):
        """L'adoption est une lecture : aucun appel d'écriture."""
        arbre = [
            {'uuid': RACINE, 'name': 'master', 'slug': 'master',
             'parent_uuid': RACINE},
        ]
        appels, _ = self._adopter(arbre)
        ecritures = [appel for appel in appels if appel[1] != 'GET']
        self.assertEqual(
            ecritures, [],
            "L'adoption ne doit rien écrire sur le PBX, jamais.")

    def test_adoption_links_each_tenant_to_its_parent(self):
        """La hiérarchie du PBX se retrouve dans la fiche."""
        arbre = [
            {'uuid': RACINE, 'name': 'master', 'slug': 'master',
             'parent_uuid': RACINE},
            {'uuid': CLIENT, 'name': 'Client Alpha', 'slug': 'alpha',
             'parent_uuid': RACINE},
        ]
        self._adopter(arbre)
        fiche_client = self.env['wazo.server.tenant'].search(
            [('remote_uuid', '=', CLIENT)])
        fiche_racine = self.env['wazo.server.tenant'].search(
            [('remote_uuid', '=', RACINE)])
        self.assertEqual(fiche_client.parent_id, fiche_racine)

    # ------------------------------------------------------------------
    # Ce qui n'y touche pas
    # ------------------------------------------------------------------

    def test_adoption_never_touches_a_known_tenant(self):
        """Une fiche connue garde son état et son jeton."""
        connue = self._create_tenant(
            name='Client Alpha', slug='alpha', remote_uuid=CLIENT,
            state='created', api_token='jeton-du-client')
        arbre = [
            {'uuid': RACINE, 'name': 'master', 'slug': 'master',
             'parent_uuid': RACINE},
            {'uuid': CLIENT, 'name': 'Client Alpha', 'slug': 'alpha',
             'parent_uuid': RACINE},
        ]
        self._adopter(arbre)
        self.assertEqual(
            self.env['wazo.server.tenant'].search_count(
                [('remote_uuid', '=', CLIENT)]), 1,
            "Un tenant déjà connu ne doit pas être dupliqué.")
        self.assertEqual(connue.api_token, 'jeton-du-client')
        self.assertEqual(connue.state, 'created')

    def test_adoption_is_idempotent(self):
        """Deux adoptions successives ne changent rien à la seconde."""
        arbre = [
            {'uuid': RACINE, 'name': 'master', 'slug': 'master',
             'parent_uuid': RACINE},
            {'uuid': CLIENT, 'name': 'Client Alpha', 'slug': 'alpha',
             'parent_uuid': RACINE},
        ]
        self._adopter(arbre)
        self._adopter(arbre)
        self.assertEqual(
            self.env['wazo.server.tenant'].search_count(
                [('remote_uuid', 'in', (RACINE, CLIENT))]), 2)

    # ------------------------------------------------------------------
    # Le cloisonnement du listage
    # ------------------------------------------------------------------

    def test_adoption_lists_from_the_root_when_the_setting_points_at_a_child(self):
        """Les réglages peuvent viser un client : on liste quand même l'arbre.

        Le listage de wazo-auth ne montre que le sous-arbre de l'en-tête. En
        partant du tenant des réglages, le maître et les autres clients
        resteraient invisibles — d'où la remontée à la racine avant de lister.
        """
        self.env['ir.config_parameter'].sudo().set_str('wazo.tenant_id', CLIENT)
        arbre = [
            {'uuid': RACINE, 'name': 'master', 'slug': 'master',
             'parent_uuid': RACINE},
            {'uuid': CLIENT, 'name': 'Client Alpha', 'slug': 'alpha',
             'parent_uuid': RACINE},
        ]
        appels, _ = self._adopter(arbre)
        listages = [appel for appel in appels
                    if appel[0] == 'auth' and appel[2] == '/tenants'
                    and appel[1] == 'GET']
        self.assertTrue(listages, "l'adoption doit lister les tenants.")
        self.assertEqual(
            listages[-1][3], RACINE,
            "Le listage final doit porter l'en-tête de la racine : sinon le "
            "maître et les autres clients restent invisibles.")
        self.assertEqual(
            self.env['wazo.server.tenant'].search_count(
                [('remote_uuid', 'in', (RACINE, CLIENT))]), 2)

    def test_adoption_handles_a_tenant_that_is_its_own_root(self):
        """Un seul tenant, qui est sa propre racine : il s'adopte aussi."""
        self.env['ir.config_parameter'].sudo().set_str('wazo.tenant_id', CLIENT)
        arbre = [
            {'uuid': CLIENT, 'name': 'Client Alpha', 'slug': 'alpha',
             'parent_uuid': CLIENT},
        ]
        self._adopter(arbre)
        self.assertEqual(
            self.env['wazo.server.tenant'].search_count(
                [('remote_uuid', '=', CLIENT)]), 1)

    def test_adoption_still_lists_when_the_tenant_record_cannot_be_read(self):
        """Remontée impossible : on liste avec l'en-tête courant, sans échouer.

        Le PBX peut refuser la fiche du tenant — un 404 de cloisonnement, une
        panne. Cela ne doit pas empêcher l'adoption : au pire, on n'adopte que
        ce que l'en-tête laisse voir.
        """
        arbre = [
            {'uuid': RACINE, 'name': 'master', 'slug': 'master',
             'parent_uuid': RACINE},
        ]
        appels, repondre = self._faux_pbx(arbre)

        def fiche_injoignable(client, service, method, path, params=None,
                              body=None, basic=None):
            if path.startswith('/tenants/') and method == 'GET':
                appels.append((service, method, path, client.tenant_id))
                raise WazoAPIError(
                    "Erreur de l'API Wazo (GET %s) : HTTP 404." % path)
            return repondre(client, service, method, path, params=params,
                            body=body, basic=basic)

        with patch.object(WazoClient, '_request', autospec=True,
                          side_effect=fiche_injoignable):
            self.env['wazo.server.tenant'].action_adopt_from_wazo()
        self.assertEqual(
            self.env['wazo.server.tenant'].search_count(
                [('remote_uuid', '=', RACINE)]), 1)

    # ------------------------------------------------------------------
    # Identifiants que Wazo accepte et que nous refusons
    # ------------------------------------------------------------------

    def test_adoption_reads_the_real_context_name_per_tenant(self):
        """Le contexte réel se lit avec l'en-tête du tenant, pas celui des réglages.

        Wazo ajoute un suffixe au nom du contexte : le nom calculé localement
        n'est qu'une approximation. Le publier tel quel dans la fiche de remise
        enverrait le client au mauvais contexte.
        """
        arbre = [
            {'uuid': RACINE, 'name': 'master', 'slug': 'master',
             'parent_uuid': RACINE},
            {'uuid': CLIENT, 'name': 'Client Alpha', 'slug': 'alpha',
             'parent_uuid': RACINE},
        ]
        appels, _ = self._adopter(arbre)
        fiche = self.env['wazo.server.tenant'].search(
            [('remote_uuid', '=', CLIENT)])
        self.assertEqual(
            fiche.remote_context_name, 'ctx-alpha-internal-%s' % CLIENT[:8],
            'Le contexte réel du tenant doit être consigné.')
        lectures = [appel for appel in appels
                    if appel[2] == '/contexts' and appel[3] == CLIENT]
        self.assertTrue(
            lectures,
            "Le contexte doit être lu avec l'en-tête du tenant lui-même.")

    def test_handover_admits_an_unknown_context_instead_of_inventing_one(self):
        """Contexte illisible : la fiche de remise le dit, elle ne l'invente pas."""
        fiche = self._create_tenant(
            name='Client Alpha', slug='alpha', remote_uuid=CLIENT,
            state='created', remote_context_name=False)
        self.assertIn('inconnu', fiche.handover_text.lower())
        self.assertNotIn(
            'ctx-alpha-internal', fiche.handover_text,
            "Le nom calculé localement ne doit pas être publié comme s'il "
            "était celui de Wazo.")

    # ------------------------------------------------------------------

    def test_adoption_sanitises_identifiers_wazo_accepts_and_we_do_not(self):
        """Un slug trop long ou à tirets ne doit pas faire échouer l'adoption."""
        arbre = [
            {'uuid': RACINE, 'name': 'master', 'slug': 'master',
             'parent_uuid': RACINE},
            {'uuid': AUTRE, 'name': 'Grand Client',
             'slug': 'grand-client-du-nord', 'parent_uuid': RACINE},
            {'uuid': CLIENT, 'name': 'Grand Client aussi',
             'slug': 'grand-client-du-sud', 'parent_uuid': RACINE},
        ]
        self._adopter(arbre)
        fiches = self.env['wazo.server.tenant'].search(
            [('remote_uuid', 'in', (AUTRE, CLIENT))])
        self.assertEqual(len(fiches), 2, "les deux fiches doivent exister.")
        self.assertEqual(len(set(fiches.mapped('slug'))), 2,
                         "deux tenants distincts ne peuvent pas partager un identifiant.")
        for fiche in fiches:
            self.assertLessEqual(len(fiche.slug), 10)
            self.assertRegex(fiche.slug, r'^[a-zA-Z0-9_]+$')