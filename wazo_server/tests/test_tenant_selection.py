# Part of the wazo_server Odoo module. See LICENSE for details.
"""Choisir le tenant à administrer, fiche par fiche.

Sur l'instance de l'**exploitant**, `wazo_server` étend les fiches qui parlent
au PBX d'un champ **tenant** : c'est lui qui décide de l'en-tête `Wazo-Tenant`
et du contexte employés, au lieu du tenant unique des réglages. Le même
`wazo.user` peut ainsi porter des postes de deux tenants différents.

Sans choix explicite, on retombe sur les réglages : c'est ce qui permet à un
**tenant** de continuer à installer `wazo_phone` seul, où le champ n'existe pas.
"""

from unittest.mock import patch

from odoo.addons.wazo_tenant.services.wazo_client import WazoClient
from odoo.tests import TransactionCase

#: Tenant des réglages : celui d'une instance mono-tenant.
MAITRE = "1a34f9bb-ddb7-4218-895b-58d1c1e36cae"
#: Tenant choisi sur la fiche.
CLIENT = "c0ffee00-1234-4abc-9def-0123456789ab"
CONTEXTE_CLIENT = "ctx-client-internal-9f8e7d6c"


class TestTenantSelection(TransactionCase):
    #: Réponse d'un PBX sans rien : aucune extension, aucune plage déclarée.
    VIDE = {"total": 0, "items": []}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env["ir.config_parameter"].sudo()
        icp.set_str("wazo.url", "https://wazo.example.com")
        icp.set_str("wazo.api_key", "jeton-administrateur")
        icp.set_str("wazo.tenant_id", MAITRE)
        icp.set_str("wazo.line_context", "ctx-maitre-internal")
        cls.tenant = cls.env["wazo.server.tenant"].create(
            {
                "name": "Client Alpha",
                "slug": "alpha",
                "state": "created",
                "remote_uuid": CLIENT,
                "remote_context_name": CONTEXTE_CLIENT,
            }
        )

    def _poste(self, **valeurs):
        """Un poste, créé sans interroger de PBX (aucune plage déclarée)."""
        valeurs.setdefault("name", "Poste Alpha")
        valeurs.setdefault("extension", "1001")
        with (
            patch.object(WazoClient, "conf", return_value=self.VIDE),
            patch.object(WazoClient, "context_id", return_value=None),
        ):
            return self.env["wazo.user"].create(valeurs)

    def _groupe(self, **valeurs):
        valeurs.setdefault("name", "Groupe Alpha")
        valeurs.setdefault("extension", "2003")
        with (
            patch.object(WazoClient, "conf", return_value=self.VIDE),
            patch.object(WazoClient, "context_id", return_value=None),
        ):
            return self.env["wazo.ring.group"].create(valeurs)

    # ------------------------------------------------------------------
    # Le tenant choisi commande l'en-tête et le contexte
    # ------------------------------------------------------------------

    def test_a_chosen_tenant_supplies_the_header(self):
        poste = self._poste(tenant_id=self.tenant.id)
        self.assertEqual(poste._wazo_tenant_uuid(), CLIENT)
        self.assertEqual(poste._wazo_client().tenant_id, CLIENT)

    def test_a_chosen_tenant_supplies_its_context(self):
        """Le poste se crée dans le contexte **du tenant**, pas dans celui des réglages."""
        poste = self._poste(tenant_id=self.tenant.id)
        self.assertEqual(poste._wazo_line_context(), CONTEXTE_CLIENT)

    def test_a_ring_group_follows_the_same_rule(self):
        """Un groupe d'appel ne peut pas viser un autre tenant que ses membres."""
        groupe = self._groupe(tenant_id=self.tenant.id)
        self.assertEqual(groupe._wazo_tenant_uuid(), CLIENT)
        self.assertEqual(groupe._wazo_line_context(), CONTEXTE_CLIENT)

    def test_two_fiches_of_two_tenants_do_not_mix(self):
        """Deux postes du même modèle, deux tenants, deux en-têtes."""
        autre = self.env["wazo.server.tenant"].create(
            {
                "name": "Client Beta",
                "slug": "beta",
                "state": "created",
                "remote_uuid": "be7a0000-0000-4000-8000-000000000001",
                "remote_context_name": "ctx-beta-internal-0000",
            }
        )
        poste_a = self._poste(name="Poste A", extension="1010", tenant_id=self.tenant.id)
        poste_b = self._poste(name="Poste B", extension="1011", tenant_id=autre.id)
        poste_sans = self._poste(name="Poste C", extension="1012")
        self.assertEqual(
            [p._wazo_tenant_uuid() for p in (poste_a, poste_b, poste_sans)],
            [CLIENT, autre.remote_uuid, MAITRE],
        )

    # ------------------------------------------------------------------
    # Sans choix, les réglages décident
    # ------------------------------------------------------------------

    def test_without_a_chosen_tenant_the_settings_win(self):
        poste = self._poste()
        self.assertEqual(poste._wazo_tenant_uuid(), MAITRE)
        self.assertEqual(poste._wazo_client().tenant_id, MAITRE)
        self.assertEqual(poste._wazo_line_context(), "ctx-maitre-internal")

    def test_a_tenant_not_created_yet_falls_back_to_the_settings(self):
        """Un tenant encore sans UUID ne peut pas fournir d'en-tête."""
        brouillon = self.env["wazo.server.tenant"].create(
            {"name": "Brouillon", "slug": "brouillon"}
        )
        poste = self._poste(tenant_id=brouillon.id)
        self.assertEqual(poste._wazo_tenant_uuid(), MAITRE)
        self.assertEqual(poste._wazo_line_context(), "ctx-maitre-internal")

    def test_a_tenant_without_context_keeps_the_settings_context(self):
        """Un contexte absent ne doit pas produire un contexte vide."""
        sans_contexte = self.env["wazo.server.tenant"].create(
            {
                "name": "Client Gamma",
                "slug": "gamma",
                "state": "created",
                "remote_uuid": "9a9a0000-0000-4000-8000-000000000002",
            }
        )
        poste = self._poste(tenant_id=sans_contexte.id)
        self.assertEqual(poste._wazo_tenant_uuid(), sans_contexte.remote_uuid)
        self.assertEqual(poste._wazo_line_context(), "ctx-maitre-internal")
