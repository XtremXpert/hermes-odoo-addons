# Part of the wazo_server Odoo module. See LICENSE for details.
"""Tests de la création d'un tenant, de bout en bout (P5.2/P5.3/P5.4).

Le client ``WazoClient`` est **remplacé par un faux serveur routé**, qui
consigne chaque appel et répond selon le service et le chemin. C'est la
séquence qui est vérifiée ici — l'ordre des appels, leur corps, l'en-tête de
tenant employé, ce qui est consigné au fil de l'eau —, pas le transport HTTP,
testé dans ``wazo_phone``.

La substitution porte sur ``_request`` avec ``autospec``, et non sur
``auth``/``conf`` : c'est la seule couture par laquelle passe **aussi**
``token()``, qui n'est ni l'un ni l'autre et irait sans cela frapper le vrai
serveur depuis un test. ``autospec`` passe l'instance du client, ce qui permet
de vérifier **pour quel tenant** chaque appel a été fait.
"""

from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.wazo_phone.services.wazo_client import WazoAPIError, WazoClient

#: Racine du serveur : c'est elle qui reçoit les tenants créés.
MAITRE = '1a34f9bb-ddb7-4218-895b-58d1c1e36cae'
NOUVEAU = 'e813ecfd-386d-4b0a-b45f-d9b0ec8d3a69'
POLITIQUE = 'a57fa5b9-e588-46b0-8aaa-8cf3b1ddab8f'
UTILISATEUR = '9c57eb12-1111-2222-3333-444455556666'


class WazoServerTestBase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env['ir.config_parameter'].sudo()
        icp.set_str('wazo.url', 'https://wazo.example.com')
        icp.set_str('wazo.api_key', 'jeton-administrateur')
        icp.set_str('wazo.tenant_id', MAITRE)

    def _create_tenant(self, **valeurs):
        valeurs.setdefault('name', 'Client Alpha')
        valeurs.setdefault('slug', 'alpha')
        return self.env['wazo.server.tenant'].create(valeurs)

    def _faux_serveur(self, erreur_sur=None, utilisateurs_distants=0,
                      lignes_distantes=0, contextes_distants=None,
                      comptes_distants=None):
        """Faux Wazo : les appels sont routés selon service et chemin.

        ``erreur_sur`` est un couple ``('auth'|'confd', chemin)`` qui fait
        échouer l'appel — pour vérifier ce qui reste consigné quand une
        séquence s'interrompt.

        Rend ``(appels, jetons, repondre)``. Chaque appel consigné est un
        quintuplet ``(service, méthode, chemin, corps, tenant)``, ``tenant``
        étant l'en-tête ``Wazo-Tenant`` employé — ou ``None``.
        """
        appels, jetons = [], []

        def repondre(client, service, method, path, params=None, body=None,
                     basic=None):
            body = body or {}
            appels.append((service, method, path, body, client.tenant_id))
            if erreur_sur and (service, path) == tuple(erreur_sur):
                raise WazoAPIError(
                    "Erreur de l'API Wazo (%s %s) : HTTP 400. Panne simulée."
                    % (method, path))
            if service == 'auth':
                if path == '/tenants' and method == 'GET':
                    return {'total': 1, 'items': [
                        {'uuid': MAITRE, 'name': 'master',
                         'slug': 'master', 'parent_uuid': MAITRE}]}
                if path == '/tenants' and method == 'POST':
                    return {'uuid': NOUVEAU, 'parent_uuid': MAITRE,
                            'name': body.get('name'),
                            'slug': body.get('slug')}
                if path == '/tenants/%s' % NOUVEAU and method == 'DELETE':
                    return None
                if path == '/policies' and method == 'GET':
                    return {'total': 1, 'items': [
                        {'uuid': POLITIQUE,
                         'slug': 'wazo_default_admin_policy'}]}
                if path == '/users' and method == 'POST':
                    return {'uuid': UTILISATEUR,
                            'username': body.get('username')}
                if path == '/users' and method == 'GET':
                    items = comptes_distants or []
                    return {'total': len(items), 'items': items}
                if path.startswith('/users/') and method == 'PUT':
                    return None
                if path == '/users/%s' % UTILISATEUR and method == 'DELETE':
                    return None
                if path == '/token' and method == 'POST':
                    jetons.append(basic)
                    return {'data': {
                        'token': 'jeton-du-tenant',
                        'expires_at': '2036-09-24T15:00:00.000000'}}
            if service == 'confd':
                if path == '/contexts' and method == 'GET':
                    items = contextes_distants or []
                    return {'total': len(items), 'items': items}
                if path == '/contexts' and method == 'POST':
                    return {'id': 7, 'name': 'ctx-alpha-internal-abcdef',
                            'label': body.get('label')}
                if path == '/contexts/7' and method == 'DELETE':
                    return None
                if path == '/users' and method == 'GET':
                    return {'total': utilisateurs_distants,
                            'items': [{'id': i} for i in
                                      range(utilisateurs_distants)]}
                if path == '/lines' and method == 'GET':
                    return {'total': lignes_distantes,
                            'items': [{'id': i} for i in
                                      range(lignes_distantes)]}
            raise AssertionError(
                'Appel inattendu au faux serveur : %s %s %s'
                % (service, method, path))

        return appels, jetons, repondre

    @staticmethod
    def _patch(repondre):
        """Substitue la couture HTTP du client par les routes simulées."""
        return patch.object(WazoClient, '_request', autospec=True,
                            side_effect=repondre)

    @staticmethod
    def _appel(appels, service, method, path):
        """Le premier appel consigné correspondant, ou une erreur claire."""
        for appel in appels:
            if (appel[0], appel[1], appel[2]) == (service, method, path):
                return appel
        raise AssertionError('Appel absent du journal : %s %s %s'
                             % (service, method, path))


@tagged('wazo_server', 'post_install', '-at_install')
class TestTenantCreation(WazoServerTestBase):

    def test_slug_is_refused_locally(self):
        """Le motif de Wazo est appliqué avant tout appel."""
        for mauvais in ('alpha-beta', 'alphabeta12', 'Alpha-Beta', 'alpha beta'):
            with self.assertRaises(ValidationError, msg='refusé : %s' % mauvais):
                self._create_tenant(slug=mauvais)

    def test_slug_of_ten_characters_is_accepted(self):
        tenant = self._create_tenant(slug='alphabeta1')
        self.assertEqual(tenant.context_name, 'ctx-alphabeta1-internal')

    def test_creation_calls_the_api_in_order(self):
        tenant = self._create_tenant()
        appels, _, repondre = self._faux_serveur()
        with self._patch(repondre):
            self.assertTrue(tenant.action_create_on_wazo())
        sequence = [(service, method, path)
                    for service, method, path, _, _ in appels]
        self.assertEqual(sequence, [
            ('auth', 'GET', '/tenants'),          # la racine
            ('auth', 'POST', '/tenants'),         # le tenant
            ('confd', 'POST', '/contexts'),       # son contexte et ses plages
            ('auth', 'POST', '/users'),           # son administrateur
            ('auth', 'GET', '/policies'),         # la politique d'administration
            ('auth', 'PUT', '/users/%s/policies/%s' % (UTILISATEUR, POLITIQUE)),
            ('auth', 'POST', '/token'),           # son jeton
        ])

    def test_context_is_created_within_the_tenant(self):
        """Le contexte naît dans le tenant neuf, avec ses plages en texte."""
        tenant = self._create_tenant()
        appels, _, repondre = self._faux_serveur()
        with self._patch(repondre):
            tenant.action_create_on_wazo()
        appel = self._appel(appels, 'confd', 'POST', '/contexts')
        self.assertEqual(appel[3]['label'], 'ctx-alpha-internal')
        self.assertEqual(appel[3]['user_ranges'],
                         [{'start': '1000', 'end': '1999'}])
        self.assertEqual(appel[3]['group_ranges'],
                         [{'start': '2000', 'end': '2099'}])
        self.assertEqual(appel[4], NOUVEAU)

    def test_admin_user_is_created_inside_the_tenant(self):
        """L'administrateur est créé **dans** le tenant, en-tête à l'appui.

        Un utilisateur créé avec l'en-tête du maître naîtrait dans le maître :
        le tenant se retrouverait sans administrateur, et le maître avec un
        compte de plus. Mesuré en direct : wazo-auth ignore le paramètre
        ``tenant_uuid`` passé en chaîne de requête, seul l'en-tête fait foi.
        """
        tenant = self._create_tenant()
        appels, _, repondre = self._faux_serveur()
        with self._patch(repondre):
            tenant.action_create_on_wazo()
        appel = self._appel(appels, 'auth', 'POST', '/users')
        self.assertEqual(appel[3]['username'], 'odoo_admin')
        self.assertEqual(appel[4], NOUVEAU,
                         "l'utilisateur naîtrait dans le maître")

    def test_policy_is_attached_to_the_tenant_administrator(self):
        """Les droits d'administration sont posés sur le compte du tenant."""
        tenant = self._create_tenant()
        appels, _, repondre = self._faux_serveur()
        with self._patch(repondre):
            tenant.action_create_on_wazo()
        appel = self._appel(appels, 'auth', 'PUT',
                            '/users/%s/policies/%s' % (UTILISATEUR, POLITIQUE))
        self.assertEqual(appel[4], NOUVEAU)

    def test_token_is_asked_with_the_tenant_password(self):
        """Le jeton est demandé avec les identifiants du tenant, en Basic."""
        tenant = self._create_tenant()
        appels, jetons, repondre = self._faux_serveur()
        with self._patch(repondre):
            tenant.action_create_on_wazo()
        self.assertEqual(len(jetons), 1)
        self.assertEqual(jetons[0][0], 'odoo_admin')
        self.assertEqual(jetons[0][1], tenant.admin_password)
        self.assertNotEqual(jetons[0][1], 'jeton-administrateur')

    def test_tenant_identifier_is_recorded_before_the_rest(self):
        """Un échec après la création du tenant laisse sa trace."""
        tenant = self._create_tenant()
        appels, _, repondre = self._faux_serveur(
            erreur_sur=('confd', '/contexts'))
        with self._patch(repondre):
            self.assertFalse(tenant.action_create_on_wazo())
        self.assertEqual(tenant.state, 'error')
        self.assertEqual(tenant.remote_uuid, NOUVEAU)
        self.assertIn('HTTP 400', tenant.error_message)

    def test_credentials_are_kept_for_the_tenant(self):
        tenant = self._create_tenant()
        appels, jetons, repondre = self._faux_serveur()
        with self._patch(repondre):
            tenant.action_create_on_wazo()
        self.assertEqual(tenant.state, 'created')
        self.assertEqual(tenant.admin_user_uuid, UTILISATEUR)
        self.assertTrue(tenant.admin_password)
        self.assertEqual(tenant.api_token, 'jeton-du-tenant')
        self.assertTrue(tenant.token_expires_at)
        self.assertEqual(tenant.context_id, 7)
        self.assertEqual(tenant.remote_context_name,
                         'ctx-alpha-internal-abcdef')

    def test_creation_is_refused_twice(self):
        tenant = self._create_tenant()
        appels, _, repondre = self._faux_serveur()
        with self._patch(repondre):
            tenant.action_create_on_wazo()
            with self.assertRaises(UserError):
                tenant.action_create_on_wazo()


@tagged('wazo_server', 'post_install', '-at_install')
class TestTenantDeletion(WazoServerTestBase):

    def _tenant_cree(self):
        tenant = self._create_tenant()
        appels, _, repondre = self._faux_serveur()
        with self._patch(repondre):
            tenant.action_create_on_wazo()
        self.assertEqual(tenant.state, 'created', 'création de départ ratée')
        return tenant

    def test_deletion_is_refused_while_the_tenant_has_postes(self):
        """Un tenant qui porte des postes ne se supprime pas par distraction."""
        tenant = self._tenant_cree()
        appels, _, repondre = self._faux_serveur(utilisateurs_distants=3,
                                                 lignes_distantes=3)
        with self._patch(repondre):
            with self.assertRaises(UserError) as ctx:
                tenant.action_delete_on_wazo()
        message = str(ctx.exception)
        self.assertIn('3 poste(s)', message)
        self.assertIn('3 ligne(s)', message)
        self.assertEqual(tenant.state, 'created')

    def test_deletion_reads_the_tenant_with_its_own_header(self):
        """La garde interroge le tenant visé, pas le serveur entier."""
        tenant = self._tenant_cree()
        appels, _, repondre = self._faux_serveur()
        with self._patch(repondre):
            tenant.action_delete_on_wazo()
        appel = self._appel(appels, 'confd', 'GET', '/users')
        self.assertEqual(appel[4], NOUVEAU)

    def test_empty_tenant_is_deleted_in_order(self):
        tenant = self._tenant_cree()
        appels, _, repondre = self._faux_serveur()
        with self._patch(repondre):
            self.assertTrue(tenant.action_delete_on_wazo())
        sequence = [(service, method, path)
                    for service, method, path, _, _ in appels
                    if method == 'DELETE']
        self.assertEqual(sequence, [
            ('confd', 'DELETE', '/contexts/7'),
            ('auth', 'DELETE', '/users/%s' % UTILISATEUR),
            ('auth', 'DELETE', '/tenants/%s' % NOUVEAU),
        ])
        self.assertEqual(tenant.state, 'new')
        self.assertFalse(tenant.remote_uuid)
        self.assertFalse(tenant.api_token)
        self.assertFalse(tenant.context_id)


@tagged('wazo_server', 'post_install', '-at_install')
class TestTenantResume(WazoServerTestBase):
    """Une création interrompue se **reprend**, elle ne recommence pas.

    Recréer le tenant produirait un doublon sur le PBX ; recréer son contexte
    en produirait un second, invisible depuis Odoo si la réponse du premier
    appel s'est perdue. La reprise relit donc ce qui existe et l'adopte.
    """

    CONTEXTE_EXISTANT = {'id': 9, 'name': 'ctx-alpha-internal-zzz',
                         'label': 'ctx-alpha-internal'}
    COMPTE_EXISTANT = {'uuid': UTILISATEUR, 'username': 'odoo_admin'}

    def _tenant_interrompu(self):
        """Un tenant dont la création a échoué après sa création sur Wazo."""
        tenant = self._create_tenant()
        appels, _, repondre = self._faux_serveur(
            erreur_sur=('confd', '/contexts'))
        with self._patch(repondre):
            self.assertFalse(tenant.action_create_on_wazo())
        self.assertEqual(tenant.state, 'error')
        self.assertEqual(tenant.remote_uuid, NOUVEAU)
        return tenant

    def test_resume_does_not_create_a_second_tenant(self):
        tenant = self._tenant_interrompu()
        appels, _, repondre = self._faux_serveur()
        with self._patch(repondre):
            self.assertTrue(tenant.action_create_on_wazo())
        sequence = [(service, method, path)
                    for service, method, path, _, _ in appels]
        self.assertNotIn(('auth', 'POST', '/tenants'), sequence)
        self.assertEqual(tenant.state, 'created')
        self.assertEqual(tenant.remote_uuid, NOUVEAU)

    def test_resume_reads_the_contexts_before_creating_one(self):
        """Recréer un contexte dont la réponse s'est perdue ferait un doublon."""
        tenant = self._tenant_interrompu()
        appels, _, repondre = self._faux_serveur()
        with self._patch(repondre):
            tenant.action_create_on_wazo()
        sequence = [(service, method, path)
                    for service, method, path, _, _ in appels]
        self.assertEqual(sequence[0], ('confd', 'GET', '/contexts'))
        self.assertIn(('confd', 'POST', '/contexts'), sequence)

    def test_resume_adopts_a_context_that_already_exists(self):
        tenant = self._tenant_interrompu()
        appels, _, repondre = self._faux_serveur(
            contextes_distants=[self.CONTEXTE_EXISTANT])
        with self._patch(repondre):
            self.assertTrue(tenant.action_create_on_wazo())
        sequence = [(service, method, path)
                    for service, method, path, _, _ in appels]
        self.assertNotIn(('confd', 'POST', '/contexts'), sequence)
        self.assertEqual(tenant.context_id, 9)
        self.assertEqual(tenant.remote_context_name, 'ctx-alpha-internal-zzz')

    def _tenant_repris(self, **valeurs):
        """Un tenant interrompu **après** la création de son administrateur.

        C'est l'état réel d'une panne survenue au moment des droits ou du
        jeton : le tenant, le contexte et le compte existent, le mot de passe
        est déjà consigné.
        """
        tenant = self._create_tenant()
        tenant.write(dict({'state': 'error', 'remote_uuid': NOUVEAU}, **valeurs))
        return tenant

    def test_resume_adopts_an_administrator_that_already_exists(self):
        """Un administrateur repris reçoit son jeton sans être recréé."""
        tenant = self._tenant_repris(admin_password='motdepasse-connu')
        appels, jetons, repondre = self._faux_serveur(
            contextes_distants=[self.CONTEXTE_EXISTANT],
            comptes_distants=[self.COMPTE_EXISTANT])
        with self._patch(repondre):
            self.assertTrue(tenant.action_create_on_wazo())
        sequence = [(service, method, path)
                    for service, method, path, _, _ in appels]
        self.assertNotIn(('auth', 'POST', '/users'), sequence)
        self.assertEqual(tenant.admin_user_uuid, UTILISATEUR)
        self.assertEqual(jetons[0][1], 'motdepasse-connu')

    def test_resume_refuses_an_administrator_whose_password_is_lost(self):
        """Sans mot de passe, pas de jeton : on le dit, on n'invente rien."""
        tenant = self._tenant_repris()
        appels, _, repondre = self._faux_serveur(
            contextes_distants=[self.CONTEXTE_EXISTANT],
            comptes_distants=[self.COMPTE_EXISTANT])
        with self._patch(repondre):
            self.assertFalse(tenant.action_create_on_wazo())
        sequence = [(service, method, path)
                    for service, method, path, _, _ in appels]
        self.assertNotIn(('auth', 'POST', '/users'), sequence)
        self.assertEqual(tenant.state, 'error')
        self.assertIn('mot de passe est inconnu', tenant.error_message)

    def test_a_created_tenant_is_not_resumed(self):
        """Un tenant abouti ne se reprend pas : la garde reste en place."""
        tenant = self._tenant_cree_pour_reprise()
        appels, _, repondre = self._faux_serveur()
        with self._patch(repondre):
            with self.assertRaises(UserError):
                tenant.action_create_on_wazo()

    def _tenant_cree_pour_reprise(self):
        tenant = self._create_tenant()
        appels, _, repondre = self._faux_serveur()
        with self._patch(repondre):
            tenant.action_create_on_wazo()
        return tenant
