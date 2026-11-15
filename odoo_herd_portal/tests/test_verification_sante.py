"""Une promotion ne se conclut que si la production répond.

Le 2026-11-14, la promotion #202 a été déclarée « done » alors que la
production répondait 503 : le retour arrière a dû être fait à la main.
Ces tests fixent le comportement attendu.
"""

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase
from odoo.tests import tagged
from odoo.tools import mute_logger

# Le portail refuse les étiquettes mouvantes : une promotion pose un digest.
DIGEST_1 = "ghcr.io/client/shop:1@sha256:" + "1" * 64
DIGEST_2 = "ghcr.io/client/shop:2@sha256:" + "2" * 64


@tagged("post_install", "-at_install")
class TestVerificationSante(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.enterClassContext(
            mute_logger(
                "odoo.addons.odoo_herd.models.k8s_cluster",
                "odoo.addons.odoo_herd.models.k8s_odoo_instance",
            )
        )
        cls.enterClassContext(
            patch.object(type(cls.env["k8s.cluster"]), "_get_k8s_client", return_value=None)
        )
        cls.cluster = cls.env["k8s.cluster"].create(
            {
                # Inactif : aucune écriture ne part vers un vrai client
                # Kubernetes. Sans cela, le client se construit depuis le
                # kubeconfig local et journalise un FutureWarning urllib3 que
                # la CI compte comme un échec.
                "active": False,
                "name": "test-cluster-sante",
                "api_endpoint": "https://k8s.example.com",
                "kubeconfig": "{}",
                "webhook_base_url": "http://odoo.example.com",
            }
        )
        cls.production = cls.env["k8s.odoo.instance"].create(
            {
                "cluster_id": cls.cluster.id,
                "name": "test-sante-prod",
                "namespace": "test-ns-sante",
                "environment": "production",
                "image": DIGEST_1,
                "url": "https://sante.example.com",
            }
        )
        cls.staging = cls.env["k8s.odoo.instance"].create(
            {
                "cluster_id": cls.cluster.id,
                "name": "test-sante-staging",
                "namespace": "test-ns-sante",
                "environment": "staging",
                "image": DIGEST_2,
                "production_instance_id": cls.production.id,
            }
        )
        cls.promotion = cls.env["k8s.odoo.promotion"].create(
            {
                "production_id": cls.production.id,
                "staging_id": cls.staging.id,
                "image": DIGEST_2,
                "previous_image": DIGEST_1,
                "state": "verifying",
            }
        )

    def _repond(self, code):
        class Reponse:
            status_code = code

        return patch("requests.get", return_value=Reponse())

    def test_site_qui_repond_conclut_la_promotion(self):
        with self._repond(200):
            self.promotion._herd_verify_health()
        self.assertEqual(self.promotion.state, "done")

    def test_site_en_503_fait_revenir_en_arriere(self):
        """5xx = aucun pod sain : on remet l'image précédente."""
        # Délai de grâce dépassé : on force l'étape à il y a une heure.
        self.promotion.write(
            {"step_started_at": fields.Datetime.now() - timedelta(hours=1)}
        )
        with self._repond(503), patch.object(
            type(self.production), "_herd_patch_image", return_value=None
        ):
            self.promotion._herd_verify_health()
        self.assertEqual(self.promotion.state, "failed")
        self.assertIn("rolled back", self.promotion.message or "")

    def test_site_en_503_dans_le_delai_attend(self):
        """Trop tôt pour conclure : la promotion reste en vérification."""
        with self._repond(503):
            self.promotion._herd_verify_health()
        self.assertEqual(self.promotion.state, "verifying")

    def test_erreur_reseau_ne_conclut_pas(self):
        with patch("requests.get", side_effect=OSError("connexion refusée")):
            self.promotion._herd_verify_health()
        self.assertEqual(self.promotion.state, "verifying")
