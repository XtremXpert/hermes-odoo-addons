"""La CI ne doit pas demander la mise à jour de modules absents de la base.

Elle calcule « les modules modifiés entre deux commits » : un module modifié
dans le dépôt mais jamais installé arrive dans la liste, et la vérification de
version — qui exige qu'un module demandé existe — fait échouer la promotion.

Constaté deux fois : social_* pour diverse-odoo (13 novembre), dms_sync et
dms_versions pour maison (15 novembre).
"""

from unittest.mock import patch

from odoo.tests import TransactionCase
from odoo.tests import tagged
from odoo.tools import mute_logger

DIGEST_A = "ghcr.io/client/shop:1@sha256:" + "1" * 64
DIGEST_B = "ghcr.io/client/shop:2@sha256:" + "2" * 64


@tagged("post_install", "-at_install")
class TestFiltreModules(TransactionCase):
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
                "active": False,
                "name": "test-cluster-filtre",
                "api_endpoint": "https://k8s.example.com",
                "kubeconfig": "{}",
                "webhook_base_url": "http://odoo.example.com",
            }
        )
        cls.prod = cls.env["k8s.odoo.instance"].create(
            {
                "cluster_id": cls.cluster.id,
                "name": "test-filtre-prod",
                "namespace": "test-ns-filtre",
                "environment": "production",
                "image": DIGEST_A,
            }
        )

    def _filtrer(self, modules):
        return self.env["k8s.odoo.promotion"]._herd_filtrer_modules_a_mettre_a_jour(
            self.prod, modules
        )

    def test_base_non_designee_ne_filtre_rien(self):
        """Sans instance désignée, on ne touche pas à la liste."""
        gardes, retires = self._filtrer("base,sale")
        self.assertEqual(gardes, "base,sale")
        self.assertEqual(retires, [])

    def test_instance_distante_ne_filtre_rien(self):
        """Une instance d'un autre cluster : son catalogue n'est pas lisible ici."""
        self.env["ir.config_parameter"].sudo().set_str("odoo_herd.self_instance_id", "999999")
        gardes, retires = self._filtrer("base,sale")
        self.assertEqual(gardes, "base,sale")
        self.assertEqual(retires, [])

    def test_module_absent_est_retire(self):
        """Sur l'instance servie par cette base, un module inconnu est écarté."""
        self.env["ir.config_parameter"].sudo().set_str(
            "odoo_herd.self_instance_id", str(self.prod.id)
        )
        gardes, retires = self._filtrer("base,module_qui_n_existe_pas")
        self.assertEqual(gardes, "base")
        self.assertEqual(retires, ["module_qui_n_existe_pas"])

    def test_module_installe_est_garde(self):
        """Un module réellement installé reste dans la liste."""
        self.env["ir.config_parameter"].sudo().set_str(
            "odoo_herd.self_instance_id", str(self.prod.id)
        )
        gardes, retires = self._filtrer("base")
        self.assertEqual(gardes, "base")
        self.assertEqual(retires, [])
