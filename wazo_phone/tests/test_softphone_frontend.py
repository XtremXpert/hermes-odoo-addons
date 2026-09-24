# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Tests des méthodes côté navigateur (P3.3b) — softphone + journal d'appels.

Le contrôleur web appelle ces méthodes sur ``res.users`` en passant l'ID de
l'utilisateur courant (le framework ``call_kw`` browse ``res.users`` avec
l'ID, puis appelle la méthode sans argument). Ces méthodes :

* ``get_wazo_softphone_config()`` — délègue à ``wazo.user.get_softphone_config``
  (config AOR/auth du softphone). Corrige le câblage du P3.3a : l'ancien
  appel passait l'ID ``res.users`` au modèle ``wazo.user`` (browse par
  coïncidence d'ID SQL, non fiable).
* ``get_wazo_call_log()`` — journal d'appels (CDR) de l'utilisateur, le plus
  récent d'abord, borné par ``limit``.
"""

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestSoftphoneFrontend(TransactionCase):

    def setUp(self):
        super().setUp()
        self.icp = self.env['ir.config_parameter'].sudo()
        self.icp.search([('key', 'in', [
            'wazo.url', 'wazo.ws_url', 'wazo.pbx_domain',
            'wazo.softphone_ws_url', 'wazo.softphone_enabled',
            'wazo.softphone_engine',
        ])]).unlink()
        self.partner = self.env['res.partner'].create({
            'name': 'Utilisateur Wazo'})
        self.user = self.env['res.users'].create({
            'name': 'Utilisateur Wazo',
            'login': 'wazo_softphone_fe',
            'partner_id': self.partner.id,
        })
        self.wizo = self.env['wazo.user'].create({
            'name': 'Utilisateur Wazo',
            'partner_id': self.partner.id,
            'extension': '1011',
            'wazo_state': 'synced',
            'sip_username': '1011',
            'sip_password': 'reg_secret_1011',
            'remote_endpoint_name': 'm0kxsfvz',
        })
        # Le lien contact -> wazo.user est posé explicitement, exactement
        # comme le flux réel action_create_wazo_user ; il n'est PAS
        # auto-populé depuis wazo.user.partner_id (pas d'inverse).
        self.partner.wazo_user_id = self.wizo

    def _cdr(self, date_start, direction, **overrides):
        values = {
            'wazo_cdr_id': date_start.day * 1000 + date_start.hour,
            'date_start': date_start,
            'date_end': date_start,
            'answered': True,
            'duration': 120,
            'caller_num': '1011',
            'caller_name': 'Utilisateur Wazo',
            'destination_num': '2000',
            'destination_name': 'Autre',
            'call_direction': direction,
        }
        values.update(overrides)
        return self.env['wazo.cdr'].create(values)

    # ------------------------------------------------------------------
    # Configuration softphone (délégation res.users -> wazo.user)
    # ------------------------------------------------------------------

    def test_config_empty_without_wazo_user(self):
        """Sans utilisateur Wazo : configuration vide."""
        u = self.env['res.users'].create({
            'name': 'Sans Wazo', 'login': 'wazo_none_fe',
        })
        self.assertEqual(u.get_wazo_softphone_config(), {})

    def test_config_delegates_to_wazo_user(self):
        """La config délègue à wazo.user (AOR ≠ auth_user, URL native)."""
        self.icp.set_str('wazo.softphone_ws_url', 'wss://relay:9876')
        self.icp.set_str('wazo.ws_url', 'wss://wazo.example/api/asterisk/ws')
        cfg = self.user.get_wazo_softphone_config()
        self.assertEqual(cfg['aor'], 'm0kxsfvz')
        self.assertEqual(cfg['auth_user'], '1011')
        # v3 : l'override relay est ignoré, on sert l'URL WebSocket de Wazo.
        self.assertEqual(cfg['ws_url'], 'wss://wazo.example/api/asterisk/ws')
        self.assertTrue(cfg['enabled'])

    def test_config_empty_when_wizo_not_synced(self):
        """wazo.user non synchronisé : configuration vide."""
        self.wizo.wazo_state = 'new'
        self.assertEqual(self.user.get_wazo_softphone_config(), {})

    def test_config_exposes_engine(self):
        """La config servie au navigateur porte le moteur SIP retenu (P3.3f)."""
        self.icp.set_str('wazo.ws_url', 'wss://wazo.example/api/asterisk/ws')
        cfg = self.user.get_wazo_softphone_config()
        self.assertEqual(cfg['engine'], 'wazo_sdk')

    # ------------------------------------------------------------------
    # Journal d'appels (CDR)
    # ------------------------------------------------------------------

    def test_call_log_empty_without_wazo_user(self):
        u = self.env['res.users'].create({
            'name': 'Sans Wazo', 'login': 'wazo_none_log',
        })
        self.assertEqual(u.get_wazo_call_log(), [])

    def test_call_log_returns_own_calls(self):
        """Les appels de l'utilisateur (extension 1011) sont retournés."""
        self._cdr(self._dt(1, 10), 'inbound')
        result = self.user.get_wazo_call_log()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['direction'], 'inbound')

    def test_call_log_excludes_other_extensions(self):
        """Les appels d'autres extensions ne sont pas retournés."""
        self._cdr(self._dt(1, 10), 'inbound')           # 1011 (moi)
        self._cdr(self._dt(1, 11), 'outbound',
                  caller_num='2000', destination_num='3000')
        result = self.user.get_wazo_call_log()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['direction'], 'inbound')

    def test_call_log_sorted_desc(self):
        """Le plus récent d'abord."""
        self._cdr(self._dt(1, 9), 'inbound')
        self._cdr(self._dt(1, 15), 'outbound')
        result = self.user.get_wazo_call_log()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['direction'], 'outbound')  # 15h (plus récent)

    def test_call_log_respects_limit(self):
        """Le bornage ``limit`` est respecté."""
        for hour in (8, 9, 10, 11):
            self._cdr(self._dt(1, hour), 'inbound')
        result = self.user.get_wazo_call_log(limit=2)
        self.assertEqual(len(result), 2)

    def test_call_log_entry_fields(self):
        """Les champs d'une entrée sont corrects (autre partie, durée…)."""
        self._cdr(self._dt(1, 10), 'inbound',
                  destination_num='1011', destination_name='Utilisateur Wazo',
                  caller_num='2000', caller_name='Léa', duration=45,
                  answered=False)
        result = self.user.get_wazo_call_log()
        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry['num'], '2000')      # appelant (autre partie)
        self.assertEqual(entry['name'], 'Léa')
        self.assertEqual(entry['duration'], 45)
        self.assertFalse(entry['answered'])
        self.assertEqual(entry['direction'], 'inbound')

    @staticmethod
    def _dt(day, hour):
        from datetime import datetime
        return datetime(2026, 9, day, hour, 0, 0)