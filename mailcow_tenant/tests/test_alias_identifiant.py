# L'alias s'édite par identifiant Mailcow : la création doit le ranger,
# sinon la fiche reste muette jusqu'à la prochaine synchronisation.
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..services.mailcow_client import MailcowClient

REPONSE = [{"msg": "Task completed", "type": "success"}]


class TestIdentifiantDUnAlias(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain = cls.env["mailcow.domain"].search([("name", "=", "dc.com")], limit=1)
        if not cls.domain:
            cls.domain = cls.env["mailcow.domain"].create({"name": "dc.com"})

    def test_la_creation_range_l_identifiant(self):
        cible = self.env["mailcow.email_address"].create({"address": "vers@dc.com"})
        alias = self.env["mailcow.alias"].create(
            {
                "domain_id": self.domain.id,
                "alias_name": "ident",
                "address_ids": [(6, 0, [cible.id])],
            }
        )
        reponses = [
            [{"msg": "alias_added", "type": "success"}],
            [{"address": "ident@dc.com", "domain": "dc.com", "id": 91, "goto": "vers@dc.com"}],
        ]
        with patch.object(MailcowClient, "_request", side_effect=reponses):
            alias.action_create_on_mailcow()
        self.assertTrue(alias.synced)
        self.assertEqual(alias.mailcow_id, "91")
