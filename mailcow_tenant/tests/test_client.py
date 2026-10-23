# Part of the mailcow_tenant Odoo module. See LICENSE for details.
"""Tests du client API Mailcow (niveau fil : urllib moqué)."""

import io
import json
import urllib.error
from unittest.mock import patch

from odoo.addons.mailcow_tenant.services.mailcow_client import MailcowAPIError
from odoo.addons.mailcow_tenant.services.mailcow_client import MailcowClient
from odoo.tests import TransactionCase
from odoo.tests import tagged


class MailcowClientTestBase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_str(
            "mailcow.base_url", "https://mail.example.com"
        )
        cls.env["ir.config_parameter"].sudo().set_str("mailcow.api_key", "test-api-key")

    def _call_with(self, method, path, payload):
        """Appele le client et retourne l'objet Request capturé."""
        body = json.dumps(payload).encode("utf-8")
        fake_response = io.BytesIO(body)
        fake_cm = type(
            "CM",
            (),
            {
                "__enter__": lambda self: fake_response,
                "__exit__": lambda self, *a: False,
            },
        )()
        with patch("urllib.request.urlopen", return_value=fake_cm) as urlopen:
            client = MailcowClient(self.env)
            client._request(method, path, payload)
        return urlopen.call_args[0][0]


@tagged("mailcow_tenant", "post_install", "-at_install")
class TestMailcowClientRequest(MailcowClientTestBase):
    def test_post_sends_url_key_header_and_json_body(self):
        request = self._call_with("POST", "/add/domain", {"domain": "ex.com"})
        self.assertEqual(request.full_url, "https://mail.example.com/api/v1/add/domain")
        self.assertEqual(request.get_header("X-API-Key"), "test-api-key")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data.decode("utf-8")), {"domain": "ex.com"})

    def test_get_sends_no_body(self):
        request = self._call_with("GET", "/get/domain/111", None)
        self.assertEqual(request.full_url, "https://mail.example.com/api/v1/get/domain/111")
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)

    def test_missing_base_url_raises(self):
        self.env["ir.config_parameter"].sudo().set_str("mailcow.base_url", False)
        client = MailcowClient(self.env)
        with self.assertRaises(MailcowAPIError):
            client._request("GET", "/get/domain/111")

    def test_http_error_raises_mailcow_api_error(self):
        error = urllib.error.HTTPError(
            "https://mail.example.com/api/v1/add/domain",
            403,
            "Forbidden",
            {},
            io.BytesIO(b"forbidden"),
        )
        with patch("urllib.request.urlopen", side_effect=error):
            client = MailcowClient(self.env)
            with self.assertRaises(MailcowAPIError):
                client._request("POST", "/add/domain", {"domain": "ex.com"})

    def test_unreachable_server_raises_mailcow_api_error(self):
        with patch(
            "urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")
        ):
            client = MailcowClient(self.env)
            with self.assertRaises(MailcowAPIError):
                client._request("GET", "/get/domain/111")
