# Part of the mailcow Odoo module. See LICENSE for details.
"""Les deux tableaux de bord, rendus pour de vrai dans un navigateur.

Les tests Python verifient les donnees, `node --test` la presentation pure ;
aucun des deux ne voit un gabarit OWL qui appelle un membre absent, ou un
composant qui meurt au chargement sans erreur cote serveur. Ce module en a
deja connu deux (voir le manifeste et l'historique du tableau de bord) : ce
test ouvre les ecrans comme un utilisateur et echoue au premier ecart.
"""

from odoo.tests import HttpCase
from odoo.tests import tagged

# Attendre un element plutot qu'un delai fixe : OWL rend apres l'appel ORM,
# et un delai fixe serait soit trop court, soit du temps perdu.
_ATTENDRE = """
const attendre = async (selecteur, texte) => {
    for (let essai = 0; essai < 150; essai++) {
        const trouves = [...document.querySelectorAll(selecteur)].filter(
            (el) => !texte || el.textContent.includes(texte));
        if (trouves.length) {
            return trouves[0];
        }
        await new Promise((fin) => setTimeout(fin, 100));
    }
    throw new Error(`Introuvable : ${selecteur} ${texte || ''}`);
};
const verifierTexte = (racine) => {
    const texte = racine.textContent;
    for (const faux of ['NaN', 'undefined', '[object Object]']) {
        if (texte.includes(faux)) {
            throw new Error(`« ${faux} » affiche dans le tableau de bord`);
        }
    }
};
"""


@tagged("mailcow", "post_install", "-at_install")
class TestTableauDeBordNavigateur(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domaine = cls.env["mailcow.domain"].create(
            {
                "name": "ecran.test",
                "quota_mb": 2048,
                "mailboxes_used": 8,
                "mailboxes_max": 10,
                "aliases_max": 20,
            }
        )
        cls.env["mailcow.mailbox"].create(
            {
                "local_part": "pleine",
                "domain_id": cls.domaine.id,
                "quota_mb": 1024,
                "quota_used_mb": 900,
                "messages": 1234,
                "active": True,
                "synced": True,
            }
        )

    def test_les_tableaux_de_bord_s_affichent_et_se_parcourent(self):
        code = (
            _ATTENDRE
            + """
(async () => {
    // Vue d'ensemble : l'alerte du plafond presque atteint, et le domaine.
    const vue = await attendre('.o_mailcow_dashboard');
    await attendre('.o_mailcow_dashboard button.card', 'plafond de boîtes');
    await attendre('.o_mailcow_dashboard tbody tr', 'ecran.test');
    verifierTexte(vue);

    // L'onglet des boites, par sa tuile : la taille se lit en unites.
    (await attendre('.o_mailcow_tuile', 'Boîtes')).click();
    await attendre('.o_mailcow_dashboard tbody tr', 'pleine@ecran.test');
    await attendre('.o_mailcow_dashboard tbody td', '900 Mo');
    verifierTexte(vue);

    // Retour aux domaines, puis le tableau du domaine clique.
    // Attendre l'en-tete propre aux domaines : sans cela, la ligne
    // « pleine@ecran.test » de l'onglet precedent repond aussi a « ecran.test ».
    (await attendre('.o_mailcow_tuile', 'Domaines')).click();
    await attendre('.o_mailcow_dashboard thead th', 'Plafond');
    (await attendre('.o_mailcow_dashboard tbody tr', 'ecran.test')).click();
    await attendre('.o_mailcow_dashboard button', 'Tous les domaines');
    const detail = await attendre('.o_mailcow_dashboard h2', 'ecran.test');
    await attendre('.o_mailcow_dashboard tbody tr', 'pleine@ecran.test');
    verifierTexte(detail.closest('.o_mailcow_dashboard'));

    console.log('test successful');
})().catch((erreur) => console.error(erreur.message));
"""
        )
        self.browser_js(
            "/odoo/action-mailcow.action_mailcow_tableau_de_bord",
            code,
            login="admin",
            timeout=60,
        )
