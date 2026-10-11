from odoo.tests import BaseCase
from odoo.tests import tagged

from ..agent_html import agent_html
from ..agent_html import values_table

# Real N3 dossier (intervention 5): one block with inline upper-case labels.
DOSSIER = (
    "Objectif : confirmer au runtime la configuration forge du broker N2. Le script lit uniquement : "
    "image, noms de ConfigMaps. IMPACT : lecture seule ; aucune ecriture. RISQUES : exposition de noms. "
    "VALIDATION : comparer la liste. RETOUR ARRIERE : sans objet ; voir https://github.com/XtremXpert/maison."
)


@tagged("post_install", "-at_install")
class TestAgentHtml(BaseCase):
    def test_inline_labels_become_sections(self):
        html = str(agent_html(DOSSIER))
        for title in ("Objectif", "Impact", "Risques", "Validation", "Retour arrière"):
            self.assertIn(f"<strong>{title}</strong>", html)
        # « lit uniquement : » is not a label, and the URL keeps its colon.
        self.assertIn("Le script lit uniquement : image", html)
        self.assertIn('href="https://github.com/XtremXpert/maison"', html)

    def test_lines_lists_code_and_bold(self):
        html = str(agent_html("Plan :\n- lancer `kubectl get`\n- **vérifier**\nfin"))
        self.assertIn(
            "<ul><li>lancer <code>kubectl get</code></li><li><strong>vérifier</strong></li></ul>",
            html,
        )
        self.assertIn("<p>fin</p>", html)

    def test_agent_text_is_escaped(self):
        html = str(
            agent_html(
                "<script>alert(1)</script> <img src=x onerror=alert(1)> "
                'javascript:alert(1) http://a.b/c"onmouseover=x'
            )
        )
        self.assertNotIn("<script", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn('href="javascript', html)
        self.assertIn('href="http://a.b/c"', html)

    def test_values_table_shows_html_as_text(self):
        html = str(
            values_table(
                {"description": False},
                {"description": "<h2>Finalité</h2><p>A &amp; B</p>"},
                {"description": "Description"},
            )
        )
        self.assertIn("<th>Avant</th><th>Après</th>", html)
        self.assertIn("<td>Description</td><td>—</td><td>Finalité A &amp; B</td>", html)
