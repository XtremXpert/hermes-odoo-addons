# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Tests du jeton d'API (P5.1) : ``POST /api/auth/0.1/token``.

Le point d'entrée est ``/token`` au **singulier** — ``/tokens`` n'accepte que
``GET`` et répond 405 en écriture, ce qui a été constaté en direct avant
d'écrire ce test. L'authentification se fait en **Basic** (``username:password``)
et non par jeton : c'est la seule façon d'obtenir un jeton, et le jeton
administrateur n'a rien à faire dans cet appel.
"""

import base64
import io
from unittest.mock import patch

from odoo.addons.wazo_phone.services.wazo_client import WazoClient
from odoo.tests import TransactionCase
from odoo.tests import tagged


class WazoTokenTestBase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env['ir.config_parameter'].sudo()
        icp.set_str('wazo.url', 'https://wazo.example.com')
        icp.set_str('wazo.api_key', 'jeton-administrateur')
        icp.set_str('wazo.tenant_id', 'uuid-tenant-1')

    def _appel_token(self, **kwargs):
        """Appelle ``token()`` et retourne la requête capturée."""
        brut = (b'{"data": {"token": "jeton-du-tenant", '
                b'"expires_at": "2036-09-24T15:00:00.000000"}}')
        fake_cm = type('CM', (), {
            '__enter__': lambda self: io.BytesIO(brut),
            '__exit__': lambda self, *a: False,
        })()
        with patch('urllib.request.urlopen',
                   return_value=fake_cm) as urlopen:
            resultat = WazoClient(self.env).token('odoo_admin', 'motdepasse',
                                                  **kwargs)
        return urlopen.call_args[0][0], resultat


@tagged('wazo_phone', 'post_install', '-at_install')
class TestWazoClientToken(WazoTokenTestBase):

    def test_token_endpoint_is_singular(self):
        request, _ = self._appel_token()
        self.assertEqual(request.full_url,
                         'https://wazo.example.com/api/auth/0.1/token')

    def test_authentication_is_basic(self):
        request, _ = self._appel_token()
        entetes = {k.lower(): v for k, v in request.header_items()}
        attendu = base64.b64encode(b'odoo_admin:motdepasse').decode()
        self.assertEqual(entetes['authorization'], 'Basic ' + attendu)

    def test_admin_token_is_not_sent_to_the_token_endpoint(self):
        """Le jeton administrateur n'a pas à être transmis pour en obtenir un."""
        request, _ = self._appel_token()
        entetes = {k.lower(): v for k, v in request.header_items()}
        self.assertNotIn('x-auth-token', entetes)

    def test_no_tenant_header_is_sent_with_credentials(self):
        """Les identifiants désignent le tenant : un en-tête le contredirait."""
        request, _ = self._appel_token()
        entetes = {k.lower(): v for k, v in request.header_items()}
        self.assertNotIn('wazo-tenant', entetes)

    def test_expiration_is_sent_and_token_returned(self):
        request, resultat = self._appel_token(expiration=315360000)
        self.assertEqual(request.data, b'{"expiration": 315360000}')
        self.assertEqual(resultat['token'], 'jeton-du-tenant')
        self.assertEqual(resultat['expires_at'], '2036-09-24T15:00:00.000000')


@tagged('wazo_phone', 'post_install', '-at_install')
class TestWazoClientRevokeToken(WazoTokenTestBase):
    """Révoquer un jeton : ``DELETE /api/auth/0.1/token/{jeton}``.

    La route ne demande **aucune authentification** (``security: - {}`` dans
    l'API de wazo-auth) : celui qui connaît le jeton peut le tuer. C'est
    exactement ce qu'il faut pour reprendre un secret fuité sur un Odoo client,
    sans connaître autre chose que le jeton lui-même. On vérifie ici la forme de
    l'appel, pas le transport.
    """

    def _appel_revocation(self, jeton='jeton-a-tuer'):
        brut = b'{"message": "Token revoked"}'
        fake_cm = type('CM', (), {
            '__enter__': lambda self: io.BytesIO(brut),
            '__exit__': lambda self, *a: False,
        })()
        with patch('urllib.request.urlopen',
                   return_value=fake_cm) as urlopen:
            resultat = WazoClient(self.env).revoke_token(jeton)
        return urlopen.call_args[0][0], resultat

    def test_revocation_is_a_delete_on_the_token_path(self):
        request, _ = self._appel_revocation()
        self.assertEqual(request.get_method(), 'DELETE')
        self.assertEqual(
            request.full_url,
            'https://wazo.example.com/api/auth/0.1/token/jeton-a-tuer')

    def test_revocation_sends_no_password(self):
        """Le jeton dans le chemin suffit : rien à prouver de plus."""
        request, _ = self._appel_revocation()
        entetes = {k.lower(): v for k, v in request.header_items()}
        self.assertNotIn('authorization', entetes)

    def test_revocation_returns_the_api_message(self):
        _, resultat = self._appel_revocation()
        self.assertEqual(resultat['message'], 'Token revoked')
