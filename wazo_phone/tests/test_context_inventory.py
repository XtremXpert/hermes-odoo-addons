# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Tests de l'inventaire du contexte (P4.4).

L'inventaire répond à une question d'exploitation : **qui existe sur ce
contexte, et qu'est-ce qui n'est rattaché à rien ?** Deux populations y sont
invisibles au quotidien : les postes rattachés à une ressource qui n'est ni un
utilisateur ni un groupe (file, conférence, renvoi, parc) et les **orphelines**,
qui occupent un numéro sans que personne ne s'en serve.

Il est reconstruit depuis le PBX — qui fait autorité — et ses lignes sont jetées
à chaque chargement : rien n'est dupliqué en base, rien ne peut diverger.
"""

from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.wazo_phone.services.wazo_client import WazoClient
from odoo.addons.wazo_phone.tests.test_extension_validation import (
    CONTEXTE,
    WazoValidationTestBase,
)

#: Un utilisateur Wazo propriétaire d'une ligne : c'est ce qui met un poste
#: **en service**.
UTILISATEUR_WAZO = [{
    'id': '7', 'firstname': 'Test', 'lastname': 'User1',
    'lines': [{'id': 12}],
}]


@tagged('wazo_phone', 'post_install', '-at_install')
class TestContextInventory(WazoValidationTestBase):
    """Inventaire : rattachements, orphelines, miroirs Odoo."""

    def _charger(self, extensions, **router_kwargs):
        """Charge l'inventaire avec un faux confd, et rend ses lignes."""
        appels = []
        route = self._router(appels, extensions=extensions, **router_kwargs)
        with patch.object(WazoClient, 'conf', side_effect=route):
            action = self.env['wazo.extension.inventory'].action_load()
        return self.env['wazo.extension.inventory'].search([]), appels, action

    def test_extension_attached_to_a_line_names_its_owner(self):
        lignes, appels, _ = self._charger(
            [{'id': 12, 'exten': '1005', 'context': CONTEXTE,
              'lines': [{'id': 12}]}],
            users=UTILISATEUR_WAZO)
        self.assertEqual(len(lignes), 1)
        self.assertEqual(lignes.attachment_kind, 'user')
        self.assertEqual(lignes.attachment_label, 'Test User1')
        self.assertFalse(lignes.is_orphan)
        # Un seul appel pour la lecture des postes, un pour leur
        # appartenance, un pour le propriétaire : pas de requête par ligne.
        self.assertEqual(appels, [
            ('GET', '/extensions'),
            ('GET', '/contexts'),
            ('GET', '/contexts/1'),
            ('GET', '/users'),
        ])

    def test_extension_without_attachment_is_orphan(self):
        """Le cas 5101 : le numéro existe, rien ne l'utilise."""
        lignes, _, _ = self._charger(
            [{'id': 18, 'exten': '5101', 'context': CONTEXTE}])
        self.assertEqual(len(lignes), 1)
        self.assertEqual(lignes.attachment_kind, 'none')
        self.assertTrue(lignes.is_orphan)
        self.assertEqual(lignes.attachment_label, '')

    def test_extension_attached_to_a_group_is_labelled(self):
        lignes, _, _ = self._charger(
            [{'id': 3, 'exten': '2000', 'context': CONTEXTE,
              'group': {'uuid': 'grp-uuid-3', 'name': 'grp-test-3'}}])
        self.assertEqual(lignes.attachment_kind, 'group')
        self.assertFalse(lignes.is_orphan)
        self.assertIn('grp-test-3', lignes.attachment_label)

    def test_extension_outside_every_declared_range_is_flagged(self):
        """1005 est dans la plage des postes, 5101 dans aucune."""
        lignes, _, _ = self._charger([
            {'id': 12, 'exten': '1005', 'context': CONTEXTE},
            {'id': 18, 'exten': '5101', 'context': CONTEXTE},
        ])
        par_numero = {ligne.extension: ligne for ligne in lignes}
        self.assertTrue(par_numero['1005'].in_declared_range)
        self.assertFalse(par_numero['5101'].in_declared_range)

    def test_extension_known_to_odoo_is_referenced(self):
        """Un poste tenu par une fiche Odoo se distingue d'une épave."""
        utilisateur = self._create_user('1006')
        utilisateur.write({'wazo_state': 'synced', 'remote_extension_id': 12})
        lignes, _, _ = self._charger(
            [{'id': 12, 'exten': '1006', 'context': CONTEXTE}])
        self.assertEqual(lignes.odoo_reference,
                         'wazo.user, %s' % utilisateur.name)

    def test_extension_unknown_to_odoo_has_no_reference(self):
        lignes, _, _ = self._charger(
            [{'id': 18, 'exten': '5101', 'context': CONTEXTE}])
        self.assertFalse(lignes.odoo_reference)

    def test_reload_replaces_the_previous_rows(self):
        """Deux chargements ne s'accumulent pas : le second fait foi."""
        self._charger([{'id': 12, 'exten': '1005', 'context': CONTEXTE}])
        lignes, _, _ = self._charger(
            [{'id': 18, 'exten': '5101', 'context': CONTEXTE}])
        self.assertEqual(len(lignes), 1)
        self.assertEqual(lignes.extension, '5101')

    def test_action_reopens_the_inventory_list(self):
        _, _, action = self._charger(
            [{'id': 18, 'exten': '5101', 'context': CONTEXTE}])
        self.assertEqual(action['res_model'], 'wazo.extension.inventory')
        self.assertEqual(action['type'], 'ir.actions.act_window')

    def test_no_users_call_when_nothing_has_a_line(self):
        """Inutile de demander les propriétaires si aucun poste n'a de ligne."""
        _, appels, _ = self._charger(
            [{'id': 18, 'exten': '5101', 'context': CONTEXTE}])
        self.assertNotIn(('GET', '/users'), appels)
