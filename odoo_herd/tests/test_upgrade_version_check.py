from unittest.mock import patch

from odoo.tests import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestUpgradeVersionCheck(TransactionCase):
    """Une mise à jour n'est « completed » que si la base a réellement bougé.

    Odoo sort en code 0 quand une mise à jour de module échoue : les erreurs SQL
    sont journalisées, le processus se termine normalement, le job Kubernetes est
    « Complete » et l'opérateur le rapporte fidèlement. Constaté le 2026-11-10 :
    ALTER TABLE refusé sur res_users, job marqué completed, contrainte d'unicité
    perdue pendant cinquante minutes.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cluster = cls.env["k8s.cluster"].create(
            {
                "name": "test-cluster-upgrade",
                "api_endpoint": "https://k8s.example.com",
                "kubeconfig": "{}",
                "webhook_base_url": "http://odoo.example.com",
            }
        )
        cls.instance = cls.env["k8s.odoo.instance"].create(
            {
                "cluster_id": cls.cluster.id,
                "name": "test-upgrade-version",
                "namespace": "test-ns",
                "environment": "production",
                "image": "ghcr.io/client/shop:1",
            }
        )

    def _upgrade(self, **vals):
        valeurs = {
            "name": "UPG/test",
            "instance_id": self.instance.id,
            "modules": "base",
        }
        valeurs.update(vals)
        return self.env["k8s.odoo.upgrade"].create(valeurs)

    def test_version_concordante_marque_completed(self):
        """Base et image d'accord : la mise à jour est valide."""
        upgrade = self._upgrade(job_name="upgrade-job-1")
        with patch.object(type(upgrade), "_ecarts_de_version", return_value=[]):
            upgrade.mark_completed()
        self.assertEqual(upgrade.state, "completed")

    def test_version_en_retard_marque_failed(self):
        """Le job a réussi mais la base n'a pas bougé : c'est un échec."""
        upgrade = self._upgrade(job_name="upgrade-job-1")
        with patch.object(
            type(upgrade),
            "_ecarts_de_version",
            return_value=["mail : base 20.0.1.0 / image 20.0.1.1"],
        ):
            upgrade.mark_completed()
        self.assertEqual(upgrade.state, "failed")
        self.assertIn("n'a pas été appliquée", upgrade.message)
        self.assertIn("mail", upgrade.message)

    def test_fiche_sans_job_n_est_pas_verifiee(self):
        """Une fiche close sans exécution réelle n'a rien à comparer.

        C'est le cas des flux simulés (tests d'autres modules) : vérifier ferait
        échouer une promotion qui n'a jamais lancé de job.
        """
        upgrade = self._upgrade()
        with patch.object(
            type(upgrade),
            "_ecarts_de_version",
            side_effect=AssertionError("ne doit pas être appelé"),
        ):
            upgrade.mark_completed()
        self.assertEqual(upgrade.state, "completed")

    def test_module_absent_de_la_base_est_un_ecart(self):
        """Un module demandé qui n'existe pas en base ne peut pas aller mieux."""
        upgrade = self._upgrade(modules="module_qui_n_existe_pas")
        ecarts = upgrade._ecarts_de_version()
        self.assertTrue(ecarts)
        self.assertIn("absent de la base", ecarts[0])

    def test_module_absent_de_l_image_n_est_pas_un_ecart(self):
        """Un module retiré de l'image n'a pas de version à comparer."""
        upgrade = self._upgrade(modules="base")
        with patch("odoo.modules.module.get_manifest", return_value=None):
            self.assertEqual(upgrade._ecarts_de_version(), [])
