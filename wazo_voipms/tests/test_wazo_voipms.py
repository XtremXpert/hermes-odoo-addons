# Part of the wazo_voipms Odoo module. See LICENSE for details.
"""Tests du pont Wazo ↔ VoIP.ms — les deux clients API sont moqués.

On patche les **noms importés dans les modules du pont** (``WazoClient``
dans le mixin de ``wazo_phone``, ``VoIPMSClient`` dans les modèles du
pont) : les classes du registre Odoo sont read-only, ``patch.object``
n'y est pas utilisable.
"""

from unittest.mock import MagicMock
from unittest.mock import patch

from odoo.addons.wazo_tenant.services.wazo_client import WazoAPIError
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase
from odoo.tests import tagged

#: Point de construction du client Wazo (mixin partagé).
WAZO_CTOR = "odoo.addons.wazo_tenant.models.wazo_extension_mixin.WazoClient"
#: Points de construction du client VoIP.ms dans le pont.
VOIPMS_CTOR_TRUNK = "odoo.addons.wazo_voipms.models.wazo_voipms_trunk.VoIPMSClient"
VOIPMS_CTOR_DID = "odoo.addons.wazo_voipms.models.voipms_did.VoIPMSClient"


class BridgeTestBase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env["ir.config_parameter"].sudo()
        icp.set_str("voipms.api_username", "u")
        icp.set_str("voipms.api_token", "t")
        icp.set_str("wazo.url", "https://wazo.example.com")
        icp.set_str("wazo.api_key", "key")
        cls.Trunk = cls.env["wazo.voipms.trunk"]
        cls.Did = cls.env["voipms.did"]
        cls.WazoUser = cls.env["wazo.user"]

    _conf_ids = {"extensions": 11, "trunks": 22, "outcalls": 33, "incalls": 44}

    def _conf_reply(self, method, path, params=None, body=None):
        if method == "POST":
            if path == "/endpoints/sip":
                return {"uuid": "uuid-ep"}
            if path == "/incalls":
                return {"id": 44, "extensions": [{"id": 55}]}
            return {"id": self._conf_ids.get(path.strip("/").split("/")[0], 0)}
        return {}

    def _wazo_mock(self):
        client = MagicMock()
        client.conf.side_effect = self._conf_reply
        return client

    def _voipms_mock(self, reply=None):
        client = MagicMock()
        client._request.return_value = reply or {"status": "success"}
        return client


@tagged("wazo_voipms", "post_install", "-at_install")
class TestTrunk(BridgeTestBase):
    def test_provision_creates_subaccount_then_wazo_chain(self):
        trunk = self.Trunk.create({"name": "TestTrunk", "pop_host": "montreal1.voip.ms"})
        voipms = self._voipms_mock(
            {"status": "success", "username": "123_x", "password": "pw"}
        )
        wazo = self._wazo_mock()
        with patch(WAZO_CTOR, return_value=wazo), patch(
            VOIPMS_CTOR_TRUNK, return_value=voipms
        ):
            trunk.action_provision()
        self.assertEqual(trunk.state, "synced")
        self.assertEqual(trunk.voipms_username, "123_x")
        self.assertEqual(trunk.remote_endpoint_uuid, "uuid-ep")
        self.assertEqual(trunk.remote_trunk_id, 22)
        self.assertEqual(trunk.remote_outcall_id, 33)
        self.assertEqual(trunk.remote_outcall_extension_id, 11)
        voipms._request.assert_called_once()
        self.assertEqual(voipms._request.call_args[0][0], "createSubAccount")
        paths = [c.args[1] for c in wazo.conf.call_args_list]
        self.assertIn("/outcalls/33/trunks", paths)
        self.assertIn("/outcalls/33/extensions/11", paths)

    def test_provision_with_existing_subaccount_skips_create(self):
        trunk = self.Trunk.create(
            {"name": "T2", "voipms_username": "u1", "voipms_password": "p1"}
        )
        voipms = self._voipms_mock()
        wazo = self._wazo_mock()
        with patch(WAZO_CTOR, return_value=wazo), patch(
            VOIPMS_CTOR_TRUNK, return_value=voipms
        ):
            trunk.action_provision()
        voipms._request.assert_not_called()
        self.assertEqual(trunk.state, "synced")

    def test_wazo_failure_marks_error_and_keeps_ids(self):
        trunk = self.Trunk.create(
            {"name": "T3", "voipms_username": "u", "voipms_password": "p"}
        )
        wazo = self._wazo_mock()
        calls = {"n": 0}

        def flaky(method, path, params=None, body=None):
            calls["n"] += 1
            if calls["n"] == 2:
                raise WazoAPIError("HTTP 500 boom")
            return self._conf_reply(method, path, params=params, body=body)

        wazo.conf.side_effect = flaky
        with patch(WAZO_CTOR, return_value=wazo):
            trunk.action_provision()
        self.assertEqual(trunk.state, "error")
        self.assertIn("500", trunk.error_message)
        self.assertEqual(trunk.remote_endpoint_uuid, "uuid-ep")

    def test_provision_twice_refused(self):
        trunk = self.Trunk.create(
            {"name": "T4", "voipms_username": "u", "voipms_password": "p"}
        )
        trunk.state = "synced"
        with self.assertRaises(UserError):
            trunk.action_provision()

    def test_unprovision_deletes_in_safe_order(self):
        trunk = self.Trunk.create(
            {"name": "T5", "voipms_username": "u", "voipms_password": "p"}
        )
        trunk.write(
            {
                "state": "synced",
                "remote_endpoint_uuid": "ep1",
                "remote_trunk_id": 7,
                "remote_outcall_id": 8,
                "remote_outcall_extension_id": 9,
            }
        )
        wazo = self._wazo_mock()
        with patch(WAZO_CTOR, return_value=wazo):
            trunk.action_unprovision()
        self.assertEqual(trunk.state, "new")
        deletes = [c.args[1] for c in wazo.conf.call_args_list if c.args[0] == "DELETE"]
        self.assertIn("/trunks/7/endpoints/sip/ep1", deletes)
        self.assertIn("/outcalls/8", deletes)

    def test_prefix_must_be_numeric(self):
        with self.assertRaises(ValidationError):
            self.Trunk.create({"name": "T6", "outbound_prefix": "abc"})


@tagged("wazo_voipms", "post_install", "-at_install")
class TestDidRouting(BridgeTestBase):
    def _make_did(self):
        return self.Did.create({"number": "4184803381"})

    def test_route_to_user(self):
        user = self.WazoUser.create(
            {"name": "Alice", "wazo_state": "synced", "remote_user_id": "5"}
        )
        did = self._make_did()
        did.write({"wazo_destination_type": "user", "wazo_user_id": user.id})
        wazo = self._wazo_mock()
        voipms = self._voipms_mock()
        with patch(WAZO_CTOR, return_value=wazo), patch(
            VOIPMS_CTOR_DID, return_value=voipms
        ):
            did.action_route_to_wazo()
        self.assertEqual(did.wazo_route_state, "routed")
        self.assertEqual(did.wazo_incall_id, 44)
        post_body = wazo.conf.call_args_list[0].kwargs.get("body") or {}
        self.assertEqual(post_body["destination"], {"type": "user", "user_id": 5})
        self.assertEqual(post_body["extensions"][0]["context"], "from-extern")
        _method, params = voipms._request.call_args[0]
        self.assertEqual(_method, "setDIDRouting")
        # Le DID est normalisé E.164 à la création (voipms.did).
        self.assertEqual(params["routing"], "sip:14184803381@wazo.example.com")

    def test_route_requires_destination(self):
        did = self._make_did()
        with self.assertRaises(ValidationError):
            did.write({"wazo_destination_type": "user"})

    def test_route_to_unsynced_user_refused(self):
        user = self.WazoUser.create({"name": "Bob"})
        did = self._make_did()
        did.write({"wazo_destination_type": "user", "wazo_user_id": user.id})
        wazo = self._wazo_mock()
        voipms = self._voipms_mock()
        with patch(WAZO_CTOR, return_value=wazo), patch(
            VOIPMS_CTOR_DID, return_value=voipms
        ):
            did.action_route_to_wazo()
        self.assertEqual(did.wazo_route_state, "error")
        self.assertIn("pas synchronisé", did.wazo_route_error)

    def test_unroute_resets_both_sides(self):
        did = self._make_did()
        did.write(
            {
                "wazo_route_state": "routed",
                "wazo_incall_id": 44,
                "wazo_incall_extension_id": 55,
            }
        )
        wazo = self._wazo_mock()
        voipms = self._voipms_mock()
        with patch(WAZO_CTOR, return_value=wazo), patch(
            VOIPMS_CTOR_DID, return_value=voipms
        ):
            did.action_unroute_from_wazo()
        self.assertEqual(did.wazo_route_state, "none")
        self.assertFalse(did.wazo_incall_id)
        _method, params = voipms._request.call_args[0]
        self.assertEqual(params["routing"], "sys:hangup")
