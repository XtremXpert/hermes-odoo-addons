#!/usr/bin/env python3
"""oca-gen-addon-readme tolérant les blocs Mermaid.

L'outil convertit les fragments `readme/` en RST puis valide le résultat avec
docutils. Un bloc ```mermaid devient ``.. code:: mermaid`` et docutils émet
« Cannot analyze code. No Pygments lexer found for "mermaid" » (WARNING/2),
que `check_rst(halt_level=2)` transforme en échec : le README est écrit mais
l'index.html ne l'est pas, et le hook pre-commit sort en erreur.

Aucun lexer Pygments « mermaid » n'existe (vérifié : Pygments 2.20/2.21, aucun
paquet PyPI). Ce lanceur enregistre un lexer de repli pour la seule validation
du RST : le HTML engendré affiche le diagramme comme bloc de code, et GitHub
rend le Mermaid directement depuis `readme/CONTEXT.md`.
"""

import sys
from pathlib import Path

from docutils.utils import code_analyzer
from pygments.lexers.special import TextLexer

_original_get_lexer_by_name = code_analyzer.get_lexer_by_name


def _get_lexer_by_name(language, *args, **kwargs):
    if str(language).strip().lower() == "mermaid":
        return TextLexer()
    return _original_get_lexer_by_name(language, *args, **kwargs)


code_analyzer.get_lexer_by_name = _get_lexer_by_name

# Le paquet installé expose un module de premier niveau « tools » ; le dossier
# tools/ du dépôt le masquerait quand ce script y est lancé.
_TOOLS_DIR = Path(__file__).resolve().parent
sys.path = [entry for entry in sys.path if Path(entry).resolve() != _TOOLS_DIR]

from tools.gen_addon_readme import gen_addon_readme  # noqa: E402

if __name__ == "__main__":
    gen_addon_readme()
