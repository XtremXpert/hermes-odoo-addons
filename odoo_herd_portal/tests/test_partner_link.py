from odoo.tests import TransactionCase
from odoo.tests import tagged

from .common import DIGEST_A
from .common import HerdPortalMixin


@tagged("post_install", "-at_install")
class TestPartnerLink(HerdPortalMixin, TransactionCase):
    """Le client d'une instance se déduit quand il peut, et se voit quand il manque."""

    @classmethod
    def setUpClass(cls):
        """Prépare la production, son staging et le client associé."""
        super().setUpClass()
        cls._herd_setup()

    def _orphan(self, name):
        return self.env["k8s.odoo.instance"].create(
            {
                "cluster_id": self.cluster.id,
                "name": name,
                "namespace": "shop",
                "environment": "production",
                "image": DIGEST_A,
            }
        )

    def test_staging_inherits_the_client_of_its_production(self):
        """Vérifie que le staging hérite du client de sa production."""
        self.assertEqual(self.staging.herd_partner_id, self.client)
        self.assertFalse(self.staging.herd_partner_missing)

    def test_explicit_client_is_not_overwritten(self):
        """Vérifie qu'un client explicitement renseigné n'est pas écrasé."""
        staging = self.env["k8s.odoo.instance"].create(
            {
                "cluster_id": self.cluster.id,
                "name": "shop-staging-b",
                "namespace": "shop",
                "environment": "staging",
                "production_instance_id": self.prod.id,
                "image": DIGEST_A,
                "herd_partner_id": self.other_client.id,
            }
        )
        self.assertEqual(staging.herd_partner_id, self.other_client)

    def test_instance_without_client_is_flagged(self):
        """Vérifie qu'une instance sans client est signalée."""
        orphan = self._orphan("orphan")
        self.assertFalse(orphan.herd_partner_id)
        self.assertTrue(orphan.herd_partner_missing)
        self.assertFalse(self.prod.herd_partner_missing)

    def test_flag_clears_once_the_client_is_set(self):
        """Vérifie que le signal disparaît dès que le client est renseigné."""
        orphan = self._orphan("orphan-two")
        orphan.write({"herd_partner_id": self.client.id})
        self.assertFalse(orphan.herd_partner_missing)
