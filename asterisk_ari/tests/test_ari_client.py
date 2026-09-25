# Part of the asterisk_ari Odoo module. See LICENSE for details.
"""Tests du client ARI (niveau fil : urllib moqué).

Contrats ARI :
- auth HTTP Basic ``app_name:api_token``
- POST/DELETE : paramètres en ``application/x-www-form-urlencoded``
- GET : paramètres en query string
- erreurs : HTTPError → ``ARIError`` avec le code ; URLError → ``ARIError``
"""

import base64
import io
import urllib.error
import urllib.parse
from unittest.mock import patch

from odoo.addons.asterisk_ari.services.ari_client import ARI
from odoo.addons.asterisk_ari.services.ari_client import ARIConfigError
from odoo.addons.asterisk_ari.services.ari_client import ARIError
from odoo.tests import TransactionCase
from odoo.tests import tagged


def _fake_cm(body=b''):
    return type('CM', (), {
        '__enter__': lambda self: io.BytesIO(body),
        '__exit__': lambda self, *a: False,
    })()


@tagged('asterisk_ari', 'post_install', '-at_install')
class TestARIClient(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_str(
            'asterisk_ari.base_url', 'http://pbx:8088/ari')
        cls.env['ir.config_parameter'].sudo().set_str(
            'asterisk_ari.app_name', 'myapp')
        cls.env['ir.config_parameter'].sudo().set_str(
            'asterisk_ari.api_token', 's3cret')
        cls.client = ARI(cls.env)

    def _call_with(self, method, path, params=None, body=b''):
        with patch('urllib.request.urlopen',
                   return_value=_fake_cm(body)) as urlopen:
            result = self.client._request(method, path, params)
        return result, urlopen.call_args[0][0]

    def test_auth_header_is_basic_b64(self):
        expected = 'Basic ' + base64.b64encode(
            b'myapp:s3cret').decode()
        self.assertEqual(self.client._auth_header(), expected)

    def test_list_apps_get(self):
        result, req = self._call_with(
            'GET', '/apps', body=b'["myapp", "other"]')
        self.assertEqual(req.full_url, 'http://pbx:8088/ari/apps')
        self.assertEqual(req.get_method(), 'GET')
        self.assertEqual(
            req.get_header('Authorization'),
            'Basic ' + base64.b64encode(b'myapp:s3cret').decode())
        self.assertEqual(result, ['myapp', 'other'])

    def test_originate_posts_form_encoded(self):
        result, req = self._call_with(
            'POST', '/calls',
            params={'endpoint': 'PJSIP/5551234', 'app': 'odoo_click',
                    'appAnswered': False, 'callerId': '+15550001234',
                    'target': '5554321'},
            body=b'{"id": "call-1"}',
        )
        self.assertEqual(req.full_url, 'http://pbx:8088/ari/calls')
        self.assertEqual(req.get_method(), 'POST')
        self.assertIn(
            'application/x-www-form-urlencoded',
            req.get_header('Content-type') or '')
        body = urllib.parse.parse_qs(req.data.decode())
        self.assertEqual(body['endpoint'], ['PJSIP/5551234'])
        self.assertEqual(body['app'], ['odoo_click'])
        self.assertEqual(body['appAnswered'], ['False'])
        self.assertEqual(body['callerId'], ['+15550001234'])
        self.assertEqual(body['target'], ['5554321'])
        self.assertEqual(result, {'id': 'call-1'})

    def test_originate_empty_result(self):
        """ARI peut renvoyer un body vide (origination différée)."""
        result, _ = self._call_with('POST', '/calls',
                                    params={'endpoint': 'PJSIP/5551234'})
        self.assertEqual(result, {})

    def test_hangup_deletes(self):
        _, req = self._call_with('DELETE', '/calls/abc-123', body=b'{}')
        self.assertEqual(req.full_url, 'http://pbx:8088/ari/calls/abc-123')
        self.assertEqual(req.get_method(), 'DELETE')

    def test_answer_posts(self):
        _, req = self._call_with('POST', '/calls/abc-123/answer', body=b'{}')
        self.assertEqual(req.full_url, 'http://pbx:8088/ari/calls/abc-123/answer')
        self.assertEqual(req.get_method(), 'POST')

    def test_http_error_raises_ari_error_with_code(self):
        err = urllib.error.HTTPError(
            'http://pbx:8088/ari/apps', 401, 'Unauthorized',
            {}, io.BytesIO(b'Unauthorized'))
        with patch('urllib.request.urlopen', side_effect=err):
            with self.assertRaises(ARIError) as ctx:
                self.client.list_apps()
        self.assertIn('401', str(ctx.exception))
        self.assertIn('Unauthorized', str(ctx.exception))

    def test_url_error_raises_ari_error(self):
        with patch('urllib.request.urlopen',
                   side_effect=urllib.error.URLError('connection refused')):
            with self.assertRaises(ARIError) as ctx:
                self.client.list_apps()
        self.assertIn('connection refused', str(ctx.exception))

    def test_invalid_json_raises_ari_error(self):
        with self.assertRaises(ARIError):
            self._call_with('GET', '/apps', body=b'<html>oops</html>')

    def test_missing_base_url_raises_config_error(self):
        self.env['ir.config_parameter'].sudo().set_str(
            'asterisk_ari.base_url', '')
        fresh = ARI(self.env)
        with self.assertRaises(ARIConfigError):
            fresh.list_apps()

    def test_missing_token_raises_config_error(self):
        self.env['ir.config_parameter'].sudo().set_str(
            'asterisk_ari.api_token', '')
        fresh = ARI(self.env)
        with self.assertRaises(ARIConfigError):
            fresh.list_apps()
