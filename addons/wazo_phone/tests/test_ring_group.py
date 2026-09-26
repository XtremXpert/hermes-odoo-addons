# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Tests des groupes d'appel Wazo (P4.3).

Un groupe d'appel prend son poste dans la plage ``group`` du contexte — ici
2000-2099, quand les postes d'utilisateurs vivent en 1000-1999. La création
côté Wazo demande **trois appels**, dans cet ordre :

1. ``POST /groups`` — le groupe (``label``, stratégie, délais) ;
2. ``POST /extensions`` — l'extension, qui doit **exister avant** d'être
   associée ;
3. ``PUT /groups/{uuid}/extensions/{extension_id}`` — l'association.

Puis, s'il y a des membres, ``PUT /groups/{uuid}/members/users`` : cet appel
**remplace l'ensemble** des membres et les désigne par **uuid** d'utilisateur —
d'où ``remote_user_uuid`` sur ``wazo.user``.
"""

from unittest.mock import patch

from odoo.addons.wazo_phone.services.wazo_client import WazoClient
from odoo.addons.wazo_phone.tests.test_extension_validation import WazoValidationTestBase
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo.tests import tagged


class _RingGroupBase(WazoValidationTestBase):
    """Fabrique de groupes et d'utilisateurs synchronisés."""

    def _create_group(self, number, **valeurs):
        valeurs.setdefault('name', 'Groupe Ventes')
        valeurs['extension'] = number
        return self.env['wazo.ring.group'].create(valeurs)

    def _membres(self, *utilisateurs, priorites=None):
        """Commandes du lien membre — qui porte la **priorité** de sonnerie."""
        priorites = list(priorites) if priorites else [10] * len(utilisateurs)
        return [(0, 0, {'user_id': utilisateur.id, 'priority': priorite})
                for utilisateur, priorite in zip(utilisateurs, priorites,
                                                  strict=False)]

    def _synced_user(self, extension, uuid):
        """Utilisateur Odoo déjà synchronisé — donc pourvu de son uuid Wazo."""
        utilisateur = self._create_user(extension)
        utilisateur.write({
            'wazo_state': 'synced',
            'remote_user_id': '7',
            'remote_user_uuid': uuid,
        })
        return utilisateur

    def _sync_capturing(self, record, **router_kwargs):
        """Comme ``_sync``, mais rend aussi les **corps** envoyés."""
        appels = []
        corps = []
        route = self._router(appels, **router_kwargs)

        def conf(method, path, params=None, body=None):
            corps.append((method, path, body))
            return route(method, path, params=params, body=body)

        with patch.object(WazoClient, 'conf', side_effect=conf), \
                patch.object(WazoClient, 'auth', side_effect=self._auth()):
            resultat = record.action_sync_wazo()
        return appels, corps, resultat


@tagged('wazo_phone', 'post_install', '-at_install')
class TestRingGroupRules(_RingGroupBase):
    """Le poste d'un groupe ne heurte ni un groupe, ni un utilisateur."""

    def test_group_number_must_be_digits(self):
        with self.assertRaises(ValidationError):
            self._create_group('20-05')

    def test_group_number_is_unique_among_groups(self):
        self._create_group('2005')
        with self.assertRaises(ValidationError):
            self._create_group('2005', name='Groupe Support')

    def test_group_number_cannot_collide_with_a_user_extension(self):
        self._create_user('2005')
        with self.assertRaises(ValidationError):
            self._create_group('2005')

    def test_user_extension_cannot_collide_with_a_group_number(self):
        """La réciproque aussi : le plan de numérotation est commun."""
        self._create_group('2005')
        with self.assertRaises(ValidationError):
            self._create_user('2005')

    def test_group_name_follows_wazos_label_pattern(self):
        """Hors ``[-_.a-zA-Z0-9 ]``, Wazo refuse : le libellé finit dans
        ``queues.conf``. Les accents en font partie — refusés."""
        with self.assertRaises(ValidationError):
            self._create_group('2005', name='Réception (accueil)')

    def test_group_name_is_bounded_to_128_characters(self):
        with self.assertRaises(ValidationError):
            self._create_group('2005', name='G' * 129)

    def test_group_name_accepts_the_allowed_characters(self):
        groupe = self._create_group('2005', name='Groupe Accueil_1.2 - bleu')
        self.assertEqual(groupe.name, 'Groupe Accueil_1.2 - bleu')

    def test_refusal_message_reads_correctly(self):
        """Le refus nomme le détenteur : « attribué **au** groupe », accordé."""
        self._create_group('2005')
        with self.assertRaises(ValidationError) as ctx:
            self._create_group('2005', name='Groupe Support')
        self.assertIn("déjà attribué au groupe d'appel",
                      str(ctx.exception))
        self.assertNotIn('à le groupe', str(ctx.exception))


@tagged('wazo_phone', 'post_install', '-at_install')
class TestRingGroupSync(_RingGroupBase):
    """Création côté Wazo : trois appels, puis les membres."""

    def test_group_requires_a_number(self):
        groupe = self._create_group(False)
        with self.assertRaises(UserError):
            groupe.action_sync_wazo()

    def test_sync_creates_group_then_extension_then_association(self):
        """L'ordre compte : l'extension doit exister avant l'association."""
        groupe = self._create_group('2005')
        appels, _, resultat = self._sync_capturing(groupe)
        self.assertTrue(resultat)
        self.assertEqual(appels, [
            ('GET', '/extensions'),
            ('GET', '/contexts'),
            ('GET', '/contexts/1'),
            ('GET', '/contexts/1/ranges/group'),
            ('POST', '/groups'),
            ('POST', '/extensions'),
            ('PUT', '/groups/grp-uuid-3/extensions/10'),
        ])
        groupe = self.env['wazo.ring.group'].browse(groupe.id)
        self.assertEqual(groupe.wazo_state, 'synced')
        self.assertEqual(groupe.remote_group_id, 'grp-uuid-3')
        self.assertEqual(groupe.remote_extension_id, 10)

    def test_group_body_carries_label_and_strategy(self):
        groupe = self._create_group(
            '2005', ring_strategy='linear', user_timeout=20, retry_delay=7)
        _, corps, _ = self._sync_capturing(groupe)
        corps_group = [c for c in corps if c[1] == '/groups'][0][2]
        self.assertEqual(corps_group['label'], 'Groupe Ventes')
        self.assertEqual(corps_group['ring_strategy'], 'linear')
        self.assertEqual(corps_group['user_timeout'], 20)
        self.assertEqual(corps_group['retry_delay'], 7)
        # ``name`` est en lecture seule côté API : le nom convivial se passe
        # par ``label``, et le ``name`` généré par Wazo ne doit pas être envoyé.
        self.assertNotIn('name', corps_group)

    def test_extension_body_carries_number_and_context(self):
        groupe = self._create_group('2005')
        _, corps, _ = self._sync_capturing(groupe)
        corps_extension = [c for c in corps
                           if c[:2] == ('POST', '/extensions')][0][2]
        self.assertEqual(corps_extension['exten'], '2005')
        self.assertEqual(corps_extension['context'],
                         self.env['ir.config_parameter'].sudo().get_str(
                             'wazo.line_context'))

    def test_members_are_sent_by_uuid(self):
        """Les membres se désignent par uuid d'utilisateur, pas par id."""
        premier = self._synced_user('1000', 'user-uuid-1')
        second = self._synced_user('1006', 'user-uuid-2')
        groupe = self._create_group(
            '2005', member_ids=self._membres(premier, second))
        _, corps, resultat = self._sync_capturing(groupe)
        self.assertTrue(resultat)
        envois = [c for c in corps if c[1].endswith('/members/users')]
        self.assertEqual(len(envois), 1)
        self.assertEqual(
            sorted(u['uuid'] for u in envois[0][2]['users']),
            ['user-uuid-1', 'user-uuid-2'])

    def test_members_carry_their_priority_in_order(self):
        """``linear`` sonne « un après l'autre » : l'ordre est la priorité."""
        premier = self._synced_user('1000', 'user-uuid-1')
        second = self._synced_user('1006', 'user-uuid-2')
        groupe = self._create_group('2005', member_ids=self._membres(
            premier, second, priorites=[20, 10]))
        _, corps, _ = self._sync_capturing(groupe)
        envois = [c for c in corps if c[1].endswith('/members/users')]
        self.assertEqual(envois[0][2]['users'], [
            {'uuid': 'user-uuid-2', 'priority': 10},
            {'uuid': 'user-uuid-1', 'priority': 20},
        ])

    def test_member_priority_defaults_to_ten(self):
        membre = self._synced_user('1000', 'user-uuid-1')
        groupe = self._create_group('2005', member_ids=self._membres(membre))
        self.assertEqual(groupe.member_ids.priority, 10)

    def test_member_is_not_repeated_in_a_group(self):
        """Le même utilisateur ne sonne pas deux fois dans le même groupe."""
        membre = self._synced_user('1000', 'user-uuid-1')
        with self.assertRaises(ValidationError):
            self._create_group(
                '2005', member_ids=self._membres(membre) + self._membres(membre))

    def test_group_without_members_sends_no_member_call(self):
        groupe = self._create_group('2005')
        appels, _, resultat = self._sync_capturing(groupe)
        self.assertTrue(resultat)
        self.assertEqual([a for a in appels if '/members/' in a[1]], [])

    def test_member_must_be_synced_first(self):
        """Sans uuid côté Wazo, aucun rattachement n'est possible."""
        membre = self._create_user('1000')
        groupe = self._create_group('2005', member_ids=self._membres(membre))
        with self.assertRaises(UserError) as ctx:
            groupe.action_sync_wazo()
        self.assertIn('synchronis', str(ctx.exception).lower())

    def test_double_sync_is_refused(self):
        groupe = self._create_group('2005')
        self._sync_capturing(groupe)
        with self.assertRaises(UserError):
            groupe.action_sync_wazo()

    def test_group_number_must_be_in_the_group_range(self):
        """1000 est dans la plage des **postes** : refusé pour un groupe."""
        groupe = self._create_group('1000')
        ctx, _ = self._expect_refusal(groupe)
        self.assertIn('postes', str(ctx.exception).lower())

    def test_group_number_outside_any_range_is_refused(self):
        groupe = self._create_group('5101')
        ctx, _ = self._expect_refusal(groupe)
        self.assertIn('groupes', str(ctx.exception).lower())

    def test_taken_group_number_is_refused(self):
        """2001 est comptée prise : extension orpheline, mais existante."""
        groupe = self._create_group('2001')
        ctx, _ = self._expect_refusal(groupe)
        self.assertIn('attribu', str(ctx.exception).lower())

    def test_delete_removes_group_then_extension(self):
        groupe = self._create_group('2005')
        self._sync_capturing(groupe)
        appels = []
        route = self._router(appels)
        with patch.object(WazoClient, 'conf', side_effect=route):
            groupe.action_delete_wazo()
        self.assertEqual(appels, [
            ('DELETE', '/groups/grp-uuid-3'),
            ('DELETE', '/extensions/10'),
        ])
        groupe = self.env['wazo.ring.group'].browse(groupe.id)
        self.assertEqual(groupe.wazo_state, 'new')
        self.assertFalse(groupe.remote_group_id)

    def test_failed_extension_still_records_the_group(self):
        """Un échec en cours de séquence ne doit pas laisser d'orphelin.

        Le groupe est créé **avant** son extension : si la création de
        l'extension échoue, l'uuid du groupe doit être conservé, sans quoi la
        ressource resterait au PBX sans trace dans Odoo — impossible à nettoyer.
        """
        groupe = self._create_group('2005')
        route = self._router([], erreur_sur=('POST', '/extensions'))
        with patch.object(WazoClient, 'conf', side_effect=route), \
                patch.object(WazoClient, 'auth', side_effect=self._auth()):
            resultat = groupe.action_sync_wazo()
        self.assertFalse(resultat)
        groupe = self.env['wazo.ring.group'].browse(groupe.id)
        self.assertEqual(groupe.wazo_state, 'error')
        self.assertIn('Panne simulée', groupe.error_message)
        self.assertEqual(groupe.remote_group_id, 'grp-uuid-3')

        appels = []
        with patch.object(WazoClient, 'conf',
                          side_effect=self._router(appels)):
            groupe.action_delete_wazo()
        self.assertEqual(appels, [('DELETE', '/groups/grp-uuid-3')])


@tagged('wazo_phone', 'post_install', '-at_install')
class TestMemberUuidRecovery(_RingGroupBase):
    """L'uuid des utilisateurs synchronisés avant l'arrivée du champ (P4.3b).

    ``remote_user_uuid`` est né avec les groupes d'appel. Un utilisateur
    synchronisé **avant** porte un uuid vide, et son état ``synced`` interdit de
    le resynchroniser : sans relecture, il ne pourrait **jamais** devenir
    membre. L'uuid se relit donc du PBX — sans rien recréer.
    """

    def test_uuid_is_read_from_the_line_when_missing(self):
        utilisateur = self._create_user('1006')
        utilisateur.write({
            'wazo_state': 'synced', 'remote_user_id': '9',
            'remote_line_id': 12})
        appels = []
        with patch.object(WazoClient, 'conf',
                          side_effect=self._router(appels)):
            uuid = utilisateur._ensure_remote_user_uuid()
        self.assertEqual(uuid, 'user-uuid-live')
        self.assertEqual(utilisateur.remote_user_uuid, 'user-uuid-live')
        self.assertEqual(appels, [('GET', '/lines/12')])

    def test_uuid_is_not_re_read_when_known(self):
        """Rien à relire : aucun appel, même pour un membre de groupe."""
        utilisateur = self._create_user('1006')
        utilisateur.write({
            'wazo_state': 'synced', 'remote_user_uuid': 'user-uuid-connu',
            'remote_line_id': 12})
        appels = []
        with patch.object(WazoClient, 'conf',
                          side_effect=self._router(appels)):
            self.assertEqual(utilisateur._ensure_remote_user_uuid(),
                             'user-uuid-connu')
        self.assertEqual(appels, [])

    def test_uuid_is_not_read_for_an_unsynchronised_user(self):
        """Rien n'existe au PBX : il n'y a aucun uuid à relire."""
        utilisateur = self._create_user('1006')
        appels = []
        with patch.object(WazoClient, 'conf',
                          side_effect=self._router(appels)):
            self.assertFalse(utilisateur._ensure_remote_user_uuid())
        self.assertEqual(appels, [])

    def test_uuid_falls_back_to_searching_lines_by_extension(self):
        """Sans id de ligne en base, la ligne se retrouve par son poste."""
        utilisateur = self._create_user('1006')
        utilisateur.write({'wazo_state': 'synced', 'remote_user_id': '9'})
        appels = []
        with patch.object(WazoClient, 'conf', side_effect=self._router(
                appels, lignes=[{'id': 12, 'exten': '1006'}])):
            uuid = utilisateur._ensure_remote_user_uuid()
        self.assertEqual(uuid, 'user-uuid-live')
        self.assertEqual(appels, [('GET', '/lines'), ('GET', '/lines/12')])

    def test_group_sync_backfills_a_member_uuid(self):
        """Le cas de la mise à niveau : le groupe se crée sans intervention."""
        membre = self._create_user('1006')
        membre.write({
            'wazo_state': 'synced', 'remote_user_id': '9',
            'remote_line_id': 12})
        groupe = self._create_group('2005', member_ids=self._membres(membre))
        _, corps, resultat = self._sync_capturing(groupe)
        self.assertTrue(resultat)
        self.assertEqual(membre.remote_user_uuid, 'user-uuid-live')
        envois = [c for c in corps if c[1].endswith('/members/users')]
        self.assertEqual(envois[0][2], {'users': [
            {'uuid': 'user-uuid-live', 'priority': 10}]})
