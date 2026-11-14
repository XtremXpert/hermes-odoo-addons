"""La queue du journal d'un job est gardée, puis archivée en pièce jointe.

Le pod d'un job disparaît avec son Job, et l'opérateur élague ses CR : sans
cette archive, la seule preuve d'une mise à jour de modules ratée disparaît
avant qu'on puisse la lire.
"""

from unittest.mock import patch

from odoo.tests import TransactionCase
from odoo.tests import tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestJournalDeJob(TransactionCase):
    """La CI compte toute ligne ERROR comme un échec : le cluster bidon de ces
    tests journalise des erreurs de connexion qu'il faut taire, et le client
    Kubernetes est remplacé par un objet nul."""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cluster = cls.env["k8s.cluster"].create(
            {
                "name": "test-cluster-journal",
                "api_endpoint": "https://k8s.example.com",
                "kubeconfig": "{}",
                "webhook_base_url": "http://odoo.example.com",
            }
        )
        cls.instance = cls.env["k8s.odoo.instance"].create(
            {
                "cluster_id": cls.cluster.id,
                "name": "test-journal",
                "namespace": "test-ns",
                "environment": "production",
                "image": "ghcr.io/client/shop:1",
            }
        )

    def setUp(self):
        super().setUp()
        self.enterContext(
            mute_logger(
                "odoo.addons.odoo_herd.models.k8s_cluster",
                "odoo.addons.odoo_herd.models.k8s_odoo_instance",
            )
        )
        self.enterContext(
            patch.object(type(self.env["k8s.cluster"]), "_get_k8s_client", return_value=None)
        )

    def _upgrade(self, **vals):
        valeurs = {"name": "UPG/journal", "instance_id": self.instance.id, "modules": "base"}
        valeurs.update(vals)
        return self.env["k8s.odoo.upgrade"].create(valeurs)

    def test_journal_garde_et_archive(self):
        """Le journal reçu devient une pièce jointe de la fiche."""
        upgrade = self._upgrade(job_name="job-1", upgrade_job_name="job-1")
        upgrade._k8s_job_prendre_journal("Traceback…\nerreur SQL\n")
        self.assertIn("erreur SQL", upgrade.log_tail or "")
        pieces = self.env["ir.attachment"].search(
            [("res_model", "=", "k8s.odoo.upgrade"), ("res_id", "=", upgrade.id)]
        )
        self.assertEqual(len(pieces), 1)
        # Odoo 20 n'expose plus `datas` : on vérifie le nom, le type et la
        # taille du contenu, ce qui prouve que le journal a bien été écrit.
        self.assertEqual(pieces.name, "job-1.log")
        self.assertEqual(pieces.mimetype, "text/plain")
        self.assertEqual(pieces.file_size, len("Traceback…\nerreur SQL\n".encode()))

    def test_journal_absent_ne_cree_rien(self):
        upgrade = self._upgrade(job_name="job-2", upgrade_job_name="job-2")
        upgrade._k8s_job_prendre_journal(None)
        self.assertFalse(upgrade.log_tail)
        pieces = self.env["ir.attachment"].search(
            [("res_model", "=", "k8s.odoo.upgrade"), ("res_id", "=", upgrade.id)]
        )
        self.assertFalse(pieces)

    def test_journal_deja_pris_ne_double_pas(self):
        """Le premier témoin fait foi : pas de seconde pièce jointe."""
        upgrade = self._upgrade(job_name="job-3", upgrade_job_name="job-3")
        upgrade._k8s_job_prendre_journal("premier")
        upgrade._k8s_job_prendre_journal("second")
        self.assertEqual(upgrade.log_tail, "premier")
        pieces = self.env["ir.attachment"].search(
            [("res_model", "=", "k8s.odoo.upgrade"), ("res_id", "=", upgrade.id)]
        )
        self.assertEqual(len(pieces), 1)
