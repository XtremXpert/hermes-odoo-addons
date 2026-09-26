# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Tests du client API Wazo (niveau fil : urllib moqué).

L'authentification passe par l'en-tête ``X-Auth-Token`` et le tenant
par ``Wazo-Tenant`` ; la casse de ces en-têtes doit être préservée.
"""

import io
import json
from unittest.mock import patch
from urllib.error import HTTPError

from odoo.addons.wazo_phone.services.wazo_client import WazoAPIError
from odoo.addons.wazo_phone.services.wazo_client import WazoClient
from odoo.tests import TransactionCase
from odoo.tests import tagged


class WazoClientTestBase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_str(
            'wazo.url', 'https://wazo.example.com')
        cls.env['ir.config_parameter'].sudo().set_str(
            'wazo.api_key', 'test-api-token')
        cls.env['ir.config_parameter'].sudo().set_str(
            'wazo.tenant_id', 'uuid-tenant-1')

    @staticmethod
    def _fake_urlopen(raw):
        """Fabrique un remplaçant de ``urllib.request.urlopen``."""
        fake_cm = type('CM', (), {
            '__enter__': lambda self: io.BytesIO(raw),
            '__exit__': lambda self, *a: False,
        })()
        return lambda *args, **kwargs: fake_cm

    def _call_with(self, method, path, params=None, body=None,
                   raw=b'{"items": []}'):
        """Appele le client et retourne l'objet Request capturé."""
        with patch('urllib.request.urlopen',
                   side_effect=self._fake_urlopen(raw)) as urlopen:
            WazoClient(self.env).conf(method, path, params=params, body=body)
        return urlopen.call_args[0][0]

    def _auth_call(self, method, path, params=None, body=None,
                   raw=b'{"items": []}'):
        """Appele le client ``auth`` et retourne l'objet Request capturé."""
        with patch('urllib.request.urlopen',
                   side_effect=self._fake_urlopen(raw)) as urlopen:
            WazoClient(self.env).auth(method, path, params=params, body=body)
        return urlopen.call_args[0][0]


@tagged('wazo_phone', 'post_install', '-at_install')
class TestWazoClientRequest(WazoClientTestBase):

    def test_builds_url_with_service_prefix(self):
        request = self._call_with('GET', '/users', params={'limit': 1})
        self.assertEqual(
            request.full_url,
            'https://wazo.example.com/api/confd/1.1/users?limit=1')

    def test_auth_token_header_is_sent_with_exact_case(self):
        request = self._call_with('GET', '/users')
        headers = {k.lower(): v for k, v in request.header_items()}
        self.assertEqual(headers['x-auth-token'], 'test-api-token')

    def test_tenant_header_is_sent(self):
        request = self._call_with('GET', '/users')
        headers = {k.lower(): v for k, v in request.header_items()}
        self.assertEqual(headers['wazo-tenant'], 'uuid-tenant-1')

    def test_post_sends_json_body(self):
        request = self._call_with('POST', '/users',
                                  body={'firstname': 'Jean'})
        self.assertEqual(request.data, json.dumps(
            {'firstname': 'Jean'}).encode('utf-8'))

    def test_call_logd_uses_call_logd_prefix(self):
        with patch('urllib.request.urlopen',
                   side_effect=self._fake_urlopen(b'{}')) as urlopen:
            WazoClient(self.env).call_logd(
                'GET', '/cdr', params={'start': '2026-09-19T00:00:00+00:00'})
        request = urlopen.call_args[0][0]
        self.assertTrue(
            request.full_url.startswith(
                'https://wazo.example.com/api/call-logd/1.0/cdr'))

    def test_auth_uses_auth_prefix(self):
        with patch('urllib.request.urlopen',
                   side_effect=self._fake_urlopen(b'{}')) as urlopen:
            WazoClient(self.env).auth(
                'POST', '/users', body={'username': '5550'})
        request = urlopen.call_args[0][0]
        self.assertEqual(
            request.full_url,
            'https://wazo.example.com/api/auth/0.1/users')

    def test_http_error_raises_wazo_api_error(self):
        error_body = b'{"message": "Forbidden", "error": "Forbidden"}'
        with patch('urllib.request.urlopen',
                   side_effect=HTTPError(
                       'https://wazo.example.com/api/confd/1.1/users',
                       403, 'Forbidden', {}, io.BytesIO(error_body))):
            with self.assertRaises(WazoAPIError) as ctx:
                WazoClient(self.env).conf('GET', '/users')
        self.assertIn('403', str(ctx.exception))

    def test_network_error_raises_wazo_api_error(self):
        with patch('urllib.request.urlopen',
                   side_effect=OSError('no route to host')):
            with self.assertRaises(WazoAPIError):
                WazoClient(self.env).conf('GET', '/users')

    def test_invalid_json_raises_wazo_api_error(self):
        with patch('urllib.request.urlopen',
                   side_effect=self._fake_urlopen(b'not-json')):
            with self.assertRaises(WazoAPIError):
                WazoClient(self.env).conf('GET', '/users')

    def test_missing_credentials_raise_wazo_api_error(self):
        self.env['ir.config_parameter'].sudo().set_str('wazo.url', '')
        with self.assertRaises(WazoAPIError):
            WazoClient(self.env).conf('GET', '/users')

    def test_credentials_can_be_overridden_per_call(self):
        client = WazoClient(
            self.env, url='https://other.example.com', api_key='other-token',
            tenant_id='')
        with patch('urllib.request.urlopen',
                   side_effect=self._fake_urlopen(b'{}')) as urlopen:
            client.conf('GET', '/users')
        request = urlopen.call_args[0][0]
        headers = {k.lower(): v for k, v in request.header_items()}
        self.assertEqual(request.full_url,
                         'https://other.example.com/api/confd/1.1/users')
        self.assertEqual(headers['x-auth-token'], 'other-token')
        self.assertNotIn('wazo-tenant', headers)

    def test_empty_response_returns_none(self):
        with patch('urllib.request.urlopen',
                   side_effect=self._fake_urlopen(b'')):
            self.assertIsNone(WazoClient(self.env).conf('GET', '/users'))
