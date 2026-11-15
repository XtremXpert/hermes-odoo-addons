"""Une sauvegarde dont le webhook s'est perdu ne doit pas figer la promotion.

Trois fois le 2026-11-15, une promotion est restée en « backing_up » alors que
le CR de sauvegarde était « Completed » : le webhook s'était perdu pendant le
redémarrage du pod, et la relecture périodique n'appliquait rien.
"""

from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

DIGEST_A = "ghcr.io/client/shop:1@sha256:" + "1" * 64
DIGEST_B = "ghcr.io/client/shop:2@sha256:" + "2" * 64


@tagged("post_install", "-at_install")
class TestRelanceSauvegarde(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.enterClassContext(
            mute_logger(
                "odoo.addons.odoo_herd.models.k8s_cluster",
                "odoo.addons.odoo_herd.models.k8s_odoo_instance",
                "odoo.addons.odoo_herd.models.k8s_job_mixin",
            )
        )
        cls.enterClassContext(
            patch.object(type(cls.env["k8s.cluster"]), "_get_k8s_client", return_value=None)
        )
        cls.cluster = cls.env["k8s.cluster"].create(
            {
                "active": False,
                "name": "test-cluster-relance",
                "api_endpoint": "https://k8s.example.com",
                "kubeconfig": "{}",
                "webhook_base_url": "http://odoo.example.com",
            }
        )
        cls.prod = cls.env["k8s.odoo.instance"].create(
            {
                "cluster_id": cls.cluster.id,
                "name": "test-relance-prod",
                "namespace": "test-ns-relance",
                "environment": "production",
                "image": DIGEST_A,
            }
        )
        cls.staging = cls.env["k8s.odoo.instance"].create(
            {
                "cluster_id": cls.cluster.id,
                "name": "test-relance-staging",
                "namespace": "test-ns-relance-staging",
                "environment": "staging",
                "production_instance_id": cls.prod.id,
                "image": DIGEST_B,
            }
        )

    def _promotion(self, etat, age_minutes, etat_sauvegarde):
        from datetime import timedelta

        from odoo import fields

        sauvegarde = self.env["k8s.odoo.backup"].create(
            {"instance_id": self.prod.id, "backup_job_name": "test-backup-relance"}
        )
        sauvegarde.state = etat_sauvegarde
        promotion = self.env["k8s.odoo.promotion"].create(
            {
                "production_id": self.prod.id,
                "staging_id": self.staging.id,
                "image": DIGEST_B,
                "production_image": DIGEST_A,
                "state": etat,
                "backup_id": sauvegarde.id,
                "step_started_at": fields.Datetime.now() - timedelta(minutes=age_minutes),
            }
        )
        return promotion, sauvegarde

    def _relancer(self, promotion):
        promotion._herd_recover_backup()

    def test_une_promotion_recente_n_est_pas_touchee(self):
        """Avant vingt minutes, on laisse le webhook arriver."""
        promotion, _ = self._promotion("backing_up", 5, "running")
        before = promotion.state
        self._relancer(promotion)
        self.assertEqual(promotion.state, before)

    def test_une_sauvegarde_terminee_fait_avancer_la_promotion(self):
        """Le CR dit terminé : la promotion avance sans attendre six heures."""
        promotion, sauvegarde = self._promotion("backing_up", 30, "running")
        with patch.object(
            type(sauvegarde),
            "_k8s_job_poll_one",
            lambda record, now: record.write({"state": "completed"}),
        ):
            self._relancer(promotion)
        self.assertEqual(sauvegarde.state, "completed")
        self.assertNotEqual(promotion.state, "backing_up")

    def test_une_sauvegarde_en_echec_fait_echouer_la_promotion(self):
        """Le CR dit échec : la promotion échoue, elle n'attend pas six heures."""
        promotion, sauvegarde = self._promotion("backing_up", 30, "running")
        with patch.object(
            type(sauvegarde),
            "_k8s_job_poll_one",
            lambda record, now: record.write({"state": "failed"}),
        ):
            self._relancer(promotion)
        self.assertEqual(promotion.state, "failed")

    def test_une_sauvegarde_qui_tourne_encore_ne_decide_rien(self):
        """La relecture ne trouve rien de neuf : on ne conclut pas au temps."""
        promotion, sauvegarde = self._promotion("backing_up", 30, "running")
        with patch.object(type(sauvegarde), "_k8s_job_poll_one", lambda record, now: None):
            self._relancer(promotion)
        self.assertEqual(promotion.state, "backing_up")
        self.assertEqual(sauvegarde.state, "running")
