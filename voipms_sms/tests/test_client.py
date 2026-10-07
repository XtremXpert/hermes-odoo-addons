# Part of the voipms_sms Odoo module. See LICENSE for details.
"""Tests du client API VoIP.ms (niveau fil : urllib moqué).

L'API REST v1 utilise des paramètres GET encodés dans l'URL
(api_username, api_password, method, ...). Aucune clé dans un header.
"""

from unittest.mock import patch

from odoo.addons.voipms_sms.services.voipms_client import VoIPMSAPIError
from odoo.addons.voipms_sms.services.voipms_client import VoIPMSClient
from odoo.tests import TransactionCase
from odoo.tests import tagged


class VoIPMSClientTestBase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_str("voipms.api_username", "test-user")
        cls.env["ir.config_parameter"].sudo().set_str("voipms.api_token", "test-token")

    def _call_with(self, method, **extra):
        """Appele le client et retourne l'objet Request capturé."""
        import io
        import json
        from urllib.parse import parse_qs
        from urllib.parse import urlparse

        body = json.dumps({"status": "success", "data": []}).encode("utf-8")
        fake_cm = type(
            "CM",
            (),
            {
                "__enter__": lambda self: io.BytesIO(body),
                "__exit__": lambda self, *a: False,
            },
        )()
        with patch("urllib.request.urlopen", return_value=fake_cm) as urlopen:
            client = VoIPMSClient(self.env)
            client._request(method, extra or None)
        request = urlopen.call_args[0][0]
        parsed = urlparse(request.full_url)
        return request, {k: v[0] for k, v in parse_qs(parsed.query).items()}


@tagged("voipms_sms", "post_install", "-at_install")
class TestVoIPMSClientRequest(VoIPMSClientTestBase):
    def test_get_sends_query_params_and_no_body(self):
        request, params = self._call_with("getDIDsInfo")
        self.assertTrue(request.full_url.startswith("https://voip.ms/api/v1/rest.php?"))
        self.assertIsNone(request.data)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(params["api_username"], "test-user")
        self.assertEqual(params["api_password"], "test-token")
        self.assertEqual(params["method"], "getDIDsInfo")

    def test_send_sms_sends_did_dst_and_message(self):
        _request, params = self._call_with(
            "sendSMS", did="14184803381", dst="14184541752", message="Bonjour"
        )
        self.assertEqual(params["method"], "sendSMS")
        self.assertEqual(params["did"], "14184803381")
        self.assertEqual(params["dst"], "14184541752")
        self.assertEqual(params["message"], "Bonjour")

    def test_missing_credentials_raise(self):
        self.env["ir.config_parameter"].sudo().set_str("voipms.api_username", False)
        client = VoIPMSClient(self.env)
        with self.assertRaises(VoIPMSAPIError):
            client._request("getDIDsInfo")

    def test_provider_failure_raises_api_error(self):
        import io
        import json

        body = json.dumps({"status": "ip_not_enabled", "message": "IP not enabled"}).encode("utf-8")
        fake_cm = type(
            "CM",
            (),
            {
                "__enter__": lambda self: io.BytesIO(body),
                "__exit__": lambda self, *a: False,
            },
        )()
        with patch("urllib.request.urlopen", return_value=fake_cm):
            client = VoIPMSClient(self.env)
            with self.assertRaises(VoIPMSAPIError):
                client._request("getDIDsInfo")

    def test_unreachable_server_raises_api_error(self):
        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            client = VoIPMSClient(self.env)
            with self.assertRaises(VoIPMSAPIError):
                client._request("getSMS", {"did": "14184803381"})
