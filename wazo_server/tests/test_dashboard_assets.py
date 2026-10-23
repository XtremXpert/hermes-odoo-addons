# Part of the wazo_server Odoo module. See LICENSE for details.
"""Le JavaScript du tableau de bord doit être déclaré et ordonné.

Même contrat que wazo_phone : un module qui importe ``@web/...`` ou
``@odoo/owl`` sans déclarer ``web`` se fait trier AVANT lui
(« waz » < « web ») et ses fichiers passent devant ``module_loader.js``,
qui définit ``odoo.define`` — le client web meurt alors sans une erreur
côté serveur.
"""

import ast
import re
from pathlib import Path

from odoo.tests import TransactionCase

CORRESPONDANCES = {"odoo": "web"}
IMPORT = re.compile(r'from\s+"(@[a-z0-9_]+)/[^"]*"')


class TestDashboardAssets(TransactionCase):
    def test_le_javascript_importe_seulement_des_modules_declares(self):
        racine = Path(__file__).resolve().parents[1]
        manifeste = ast.literal_eval((racine / "__manifest__.py").read_text())
        declarees = set(manifeste.get("depends", []))

        manquantes = {}
        for fichier in sorted((racine / "static" / "src").rglob("*.js")):
            source = fichier.read_text(encoding="utf-8")
            for prefixe in IMPORT.findall(source):
                module = CORRESPONDANCES.get(prefixe[1:], prefixe[1:])
                if module in declarees:
                    continue
                manquantes.setdefault(module, set()).add(
                    str(fichier.relative_to(racine))
                )
        self.assertFalse(
            manquantes,
            "Modules importés par le JavaScript sans figurer dans les "
            "dépendances du manifeste : %s" % manquantes,
        )

    def test_le_javascript_est_ordonne_apres_le_chargeur_de_modules(self):
        racine = Path(__file__).resolve().parents[1]
        manifeste = ast.literal_eval((racine / "__manifest__.py").read_text())
        commandes = manifeste["assets"]["web.assets_backend"]
        ordonne = any(
            isinstance(commande, tuple)
            and commande[0] == "after"
            and "module_loader.js" in commande[1]
            for commande in commandes
        )
        self.assertTrue(
            ordonne,
            "Le JavaScript doit être déclaré ('after', "
            "'web/static/src/module_loader.js', ...).",
        )
