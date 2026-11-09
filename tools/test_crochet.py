#!/usr/bin/env python3
"""Le crochet de pré-commit tient-il ses promesses ?

Un crochet qu'on ne teste pas pourrit en silence : on le croit actif alors
qu'il ne bloque plus rien, et le premier à s'en apercevoir est le coureur de la
CI, après la poussée.

Ce script clone le dépôt dans un dossier jetable, y pose le crochet, introduit
une faute de chaque sorte qu'il surveille, et **exige** qu'il refuse le commit.
Il exige aussi qu'il l'accepte quand il n'y a pas de faute : un crochet qui
refuse tout ne protège rien, il bloque.

Aucune valeur d'identifiant n'est lue ni écrite ici.

Usage : python3 tools/test_crochet.py [-v]

Le clone est bâti sur HEAD, pas sur l'arbre de travail : ce test éprouve donc le
crochet **committé**. Un outil modifié mais non committé n'est pas éprouvé — il
faut committer avant de se fier à un vert.
"""

# Outil en ligne de commande, lancé hors d'Odoo : il parle à son terminal,
# « print » est sa sortie, pas un journal.
# pylint: disable=print-used

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
VERBEUX = "-v" in sys.argv

# Chaque cas : un nom, la faute à introduire, l'étape qui doit la refuser.
# Les étapes sont celles du crochet, dans son ordre :
#   ruff · compilation · XML · restes · verrou Odoo · tests JS
CAS = (
    ("ruff : une ligne trop longue", "ligne-longue"),
    ("compilation : un fichier illisible", "syntaxe"),
    ("XML : un fichier mal fermé", "xml"),
    ("restes : une règle d'accès à cinq champs", "csv"),
)


def dire(texte: str = "") -> None:
    print(texte, flush=True)


def git(dossier: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=dossier, capture_output=True, text=True, check=False)


def introduire(dossier: Path, genre: str) -> str:
    """Écrit la faute dans le clone. Rend le chemin touché, en relatif."""
    if genre == "ligne-longue":
        # Un fichier de modèle, surtout pas un manifeste : la config exempte
        # « **/__manifest__.py » et « **/tests/*.py » d'E501, à dessein. Une
        # faute posée là ne dirait rien du crochet.
        cible = dossier / "mailcow_tenant" / "models" / "res_config_settings.py"
        cible.write_text(cible.read_text() + f"\n# {'x' * 140}\n")
    elif genre == "syntaxe":
        cible = dossier / "voipms_sms" / "models" / "syntaxe_cassee.py"
        cible.write_text("def oups(:\n")
    elif genre == "xml":
        cible = dossier / "asterisk_ari" / "security" / "casse.xml"
        cible.write_text("<odoo><data>\n")
    elif genre == "csv":
        cible = dossier / "mailcow_tenant" / "security" / "ir.access.csv"
        regle = "regle_cassee,un modele,trop,peu,de,champs,ici"
        cible.write_text(cible.read_text().rstrip("\n") + "\n" + regle + "\n")
    else:
        raise ValueError(genre)
    return str(cible.relative_to(dossier))


def nettoyer(dossier: Path, chemin: str) -> None:
    (dossier / chemin).unlink(missing_ok=True)


def crochet_sur(dossier: Path) -> None:
    """Pose le crochet exactement comme le dépôt le prescrit."""
    git(dossier, "config", "core.hooksPath", "tools/hooks")
    git(dossier, "config", "user.email", "test@localhost")
    git(dossier, "config", "user.name", "essai")


def commit_blanc(dossier: Path, message: str) -> subprocess.CompletedProcess:
    """Un commit sans faute : il doit passer. Sert aussi de référence."""
    marqueur = dossier / "outils_jetable.txt"
    marqueur.write_text(message + "\n")
    git(dossier, "add", "-A")
    return git(dossier, "commit", "-m", message)


def main() -> int:
    if not (RACINE / "tools" / "hooks" / "pre-commit").exists():
        dire("Le crochet est absent : il n'y a rien à éprouver.")
        return 2

    temporaire = Path(tempfile.mkdtemp(prefix="test-crochet-"))
    clone = temporaire / "depot"
    dire(f"Clone jetable : {clone}")
    try:
        # Clone LOCAL : aucun réseau, et le poc git-ignoré n'est pas copié
        # (git ne copie que ce qu'il suit).
        fait = subprocess.run(
            ["git", "clone", "--quiet", str(RACINE), str(clone)],
            capture_output=True,
            text=True,
            check=False,
        )
        if fait.returncode != 0:
            dire(f"Le clone a échoué : {fait.stderr.strip()}")
            return 2
        crochet_sur(clone)

        dire("\n1. Sans faute, le crochet doit laisser passer.")
        reference = commit_blanc(clone, "reference : rien a signaler")
        if reference.returncode != 0:
            dire("   ÉCHEC : le crochet refuse un commit propre.")
            suite = (reference.stderr or reference.stdout).strip()[-600:]
            dire("   " + suite.replace("\n", "\n   "))
            return 1
        dire("   il laisse passer.")

        dire("\n2. Avec une faute, il doit refuser — et dire laquelle.")
        echecs = 0
        for titre, genre in CAS:
            chemin = introduire(clone, genre)
            fait = commit_blanc(clone, f"faute volontaire : {titre}")
            sortie = (fait.stdout or "") + (fait.stderr or "")
            if fait.returncode == 0:
                dire(f"   ÉCHEC : {titre} — le commit est passé.")
                echecs += 1
            elif "Commit refusé" not in sortie:
                dire(f"   ÉCHEC : {titre} — refusé, mais pas par le crochet.")
                echecs += 1
            else:
                # L'étape fautive doit être nommée dans la sortie.
                etape = genre if genre != "ligne-longue" else "ruff"
                nom = {"syntaxe": "compilation", "csv": "restes", "ruff": "ruff"}.get(etape, etape)
                nomme = nom in sortie
                dire(f"   {'refusé' if nomme else 'refusé (étape non nommée)'} : {titre}")
                echecs += 0 if nomme else 1
            nettoyer(clone, chemin)
            git(clone, "reset", "--quiet")

        dire("\n3. Le dossier jetable est retiré.")
        return 1 if echecs else 0
    finally:
        shutil.rmtree(temporaire, ignore_errors=True)


if __name__ == "__main__":
    code = main()
    dire(
        "\nVerdict : le crochet tient ses promesses."
        if code == 0
        else "\nVerdict : le crochet ne tient pas ses promesses (voir ci-dessus)."
    )
    sys.exit(code)
