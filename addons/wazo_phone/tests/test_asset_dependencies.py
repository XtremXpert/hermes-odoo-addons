"""Le manifeste doit déclarer les modules dont dépend le JavaScript du client.

Un module qui importe ``@web/...`` ou ``@odoo/owl`` sans déclarer ``web`` se fait
ordonner AVANT lui dans le paquet d'actifs : ses fichiers passent devant
``module_loader.js``, qui définit ``odoo.define``. Résultat : le client web meurt
au chargement, sans une seule erreur côté serveur, et sans qu'aucun test Python
ni Node ne voie quoi que ce soit.
"""

import ast
import re
from pathlib import Path

from odoo.tests import TransactionCase

# « @odoo/... » est servi par le module « web ». Les autres préfixes portent le
# nom du module qui fournit le fichier importé.
CORRESPONDANCES = {'odoo': 'web'}

IMPORT = re.compile(r'from\s+"(@[a-z0-9_]+)/[^"]*"')


class TestAssetDependencies(TransactionCase):
    def test_le_javascript_importe_seulement_des_modules_declares(self):
        racine = Path(__file__).resolve().parents[1]
        manifeste = ast.literal_eval((racine / '__manifest__.py').read_text())
        déclarées = set(manifeste.get('depends', []))
        propres = {racine.name}

        manquantes = {}
        for fichier in sorted((racine / 'static' / 'src').rglob('*.js')):
            source = fichier.read_text(encoding='utf-8')
            for préfixe in IMPORT.findall(source):
                module = CORRESPONDANCES.get(préfixe[1:], préfixe[1:])
                if module in déclarées or module in propres:
                    continue
                manquantes.setdefault(module, set()).add(
                    str(fichier.relative_to(racine)))

        self.assertFalse(
            manquantes,
            "Ces modules sont importés par le JavaScript du client sans figurer "
            "dans les dépendances du manifeste — nos fichiers seront alors "
            "ordonnés avant le chargeur de modules dans le paquet d'actifs : %s"
            % {module: sorted(fichiers)
               for module, fichiers in sorted(manquantes.items())})

    def test_le_javascript_est_ordonne_apres_le_chargeur_de_modules(self):
        """Le tri des modules place wazo_phone avant web (« waz » < « web »).

        Sans ordre explicite, nos fichiers passeraient donc devant
        ``module_loader.js``, qui définit ``odoo.define`` : le client web meurt
        au chargement, sans une seule erreur côté serveur.
        """
        racine = Path(__file__).resolve().parents[1]
        manifeste = ast.literal_eval((racine / '__manifest__.py').read_text())
        commandes = manifeste['assets']['web.assets_backend']

        ordonné = any(
            isinstance(commande, tuple)
            and commande[0] == 'after'
            and len(commande) == 3
            and 'module_loader.js' in commande[1]
            for commande in commandes)

        self.assertTrue(
            ordonné,
            "Le JavaScript du client doit être déclaré avec une commande "
            "('after', 'web/static/src/module_loader.js', ...). Sans elle, Odoo "
            "ordonne ce module avant « web » et le client web ne démarre pas.")

