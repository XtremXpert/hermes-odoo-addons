# Part of the wazo_tenant Odoo module. See LICENSE for details.
"""Files, conférences, IVR, messageries, parcs : cycle de vie complet.

Le client Wazo est moqué au fil : chaque réponse suit le chemin appelé
(mesuré sur confd 1.1). Les classes du registre Odoo étant read-only,
le moquage se fait sur la classe importée, comme pour les usagers.
"""

from unittest.mock import patch

from odoo.addons.wazo_tenant.services.wazo_client import WazoClient
from odoo.tests import TransactionCase
from odoo.tests import tagged

#: Réponses par chemin : id séquentiel distinct par ressource.
REPLIES = {
    ("POST", "/queues"): {"id": 61},
    ("POST", "/conferences"): {"id": 62},
    ("POST", "/ivr"): {"id": 63},
    ("POST", "/voicemails"): {"id": 64},
    ("POST", "/parkinglots"): {"id": 65},
    ("POST", "/extensions"): {"id": 60},
    # Le contexte du parc, résolu/créé au maître : Wazo 26 génère un nom
    # interne, pas le libellé (mesuré).
    ("GET", "/contexts"): {"items": []},
    ("POST", "/contexts"): {"id": 67, "name": "ctx-master-parking-test"},
}
_NEXT_ID = [66]


def _conf_reply(method, path, params=None, body=None):
    cle = (method, path)
    if cle in REPLIES:
        return REPLIES[cle]
    if method == "POST":
        # Chemin imprévu : un id unique, jamais un crash de test.
        _NEXT_ID[0] += 1
        return {"id": _NEXT_ID[0]}
    # GET /extensions, /contexts : rien à reprendre.
    return {"items": []}


@tagged("wazo_tenant", "post_install", "-at_install")
class TestWazoObjects(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_str("wazo.line_context", "default")

    def _client_mock(self):
        import unittest.mock as mock

        client = mock.MagicMock()
        client.conf.side_effect = _conf_reply
        return client

    def _with_mock(self):
        client = self._client_mock()
        patcher = patch.object(WazoClient, "conf", side_effect=client.conf.side_effect)
        return client, patcher

    def test_queue_sync_and_delete(self):
        Queue = self.env["wazo.queue"]
        user = self.env["wazo.user"].create(
            {"name": "Agent", "wazo_state": "synced", "remote_user_uuid": "u-1"}
        )
        queue = Queue.create(
            {"name": "Support", "extension": "3000", "member_ids": [(6, 0, [user.id])]}
        )
        _client, patcher = self._with_mock()
        with patcher:
            self.assertTrue(queue.action_sync_wazo())
        self.assertEqual(queue.wazo_state, "synced")
        self.assertEqual(queue.remote_queue_id, 61)
        self.assertEqual(queue.remote_extension_id, 60)
        # Re-sync refusé : idempotence par l'état.
        from odoo.exceptions import UserError

        with self.assertRaises(UserError):
            queue.action_sync_wazo()
        # Suppression : membre dissocié, extension, file.
        _client, patcher = self._with_mock()
        with patcher:
            self.assertTrue(queue.action_delete_wazo())
        self.assertEqual(queue.wazo_state, "new")
        self.assertFalse(queue.remote_queue_id)

    def test_conference_sync_and_delete(self):
        conference = self.env["wazo.conference"].create(
            {"name": "Salle conseil", "extension": "4000", "pin": "1234"}
        )
        _client, patcher = self._with_mock()
        with patcher:
            self.assertTrue(conference.action_sync_wazo())
        self.assertEqual(conference.wazo_state, "synced")
        self.assertEqual(conference.remote_conference_id, 62)
        _client, patcher = self._with_mock()
        with patcher:
            self.assertTrue(conference.action_delete_wazo())
        self.assertEqual(conference.wazo_state, "new")

    def test_ivr_sync_and_delete(self):
        ivr = self.env["wazo.ivr"].create({"name": "Accueil"})
        _client, patcher = self._with_mock()
        with patcher:
            self.assertTrue(ivr.action_sync_wazo())
        self.assertEqual(ivr.wazo_state, "synced")
        self.assertEqual(ivr.remote_ivr_id, 63)
        _client, patcher = self._with_mock()
        with patcher:
            self.assertTrue(ivr.action_delete_wazo())
        self.assertEqual(ivr.wazo_state, "new")

    def test_voicemail_sync_refuses_associated_on_delete(self):
        from odoo.addons.wazo_tenant.services.wazo_client import WazoAPIError

        voicemail = self.env["wazo.voicemail"].create(
            {"name": "Boîte accueil", "number": "5000"}
        )
        _client, patcher = self._with_mock()
        with patcher:
            self.assertTrue(voicemail.action_sync_wazo())
        self.assertEqual(voicemail.remote_voicemail_id, 64)
        # Suppression refusée : confd répond 400 quand la boîte est
        # encore associée à un usager (mesuré).
        import unittest.mock as mock

        client = mock.MagicMock()

        def refuse(method, path, params=None, body=None):
            if method == "DELETE":
                raise WazoAPIError("HTTP 400. associée", status=400)
            return _conf_reply(method, path, params=params, body=body)

        client.conf.side_effect = refuse
        with patch.object(WazoClient, "conf", side_effect=refuse):
            self.assertFalse(voicemail.action_delete_wazo())
        self.assertEqual(voicemail.wazo_state, "error")
        self.assertIn("400", voicemail.error_message)

    def test_parking_sync_and_delete(self):
        parking = self.env["wazo.parking"].create(
            {"name": "Parc", "extension": "700", "slots_start": "701", "slots_end": "710"}
        )
        _client, patcher = self._with_mock()
        with patcher:
            self.assertTrue(parking.action_sync_wazo())
        self.assertEqual(parking.wazo_state, "synced")
        self.assertEqual(parking.remote_parking_lot_id, 65)
        _client, patcher = self._with_mock()
        with patcher:
            self.assertTrue(parking.action_delete_wazo())
        self.assertEqual(parking.wazo_state, "new")

    def test_parking_slots_must_be_ordered_numbers(self):
        from odoo.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            self.env["wazo.parking"].create(
                {"name": "Vide", "extension": "701", "slots_start": "710", "slots_end": "701"}
            )
        with self.assertRaises(ValidationError):
            self.env["wazo.parking"].create(
                {"name": "Lettres", "extension": "701", "slots_start": "a", "slots_end": "z"}
            )
