#!/usr/bin/env python3
"""Compare les modules installés en base à ceux qui existent dans le code.

Un module resté « installé » alors que son code a disparu du disque occupe une
fiche en base et s'affiche dans la liste des applications : c'est un fantôme.
L'inverse — un module du dépôt installé nulle part — signale un oubli.

    python3 tools/modules_fantomes.py -d odoo20
    python3 tools/modules_fantomes.py -d odoo20_neuve --utilisateur bvezina
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
NOS_MODULES = ("asterisk_ari", "mailcow_admin", "voipms_sms", "wazo_phone", "wazo_server")

# Les racines RÉELLEMENT chargées. `enterprise/` n'y est pas : ses modules
# n'existent donc pas pour Odoo, ce qu'il consigne justement en « uninstallable ».
RACINES_ADDONS = ("addons", "odoo/addons", "odoo/odoo/addons", "design-themes", ".")


def modules_du_code() -> set[str]:
    trouves: set[str] = set()
    for racine in RACINES_ADDONS:
        base = RACINE / racine
        if not base.is_dir():
            continue
        for dossier in (d for d in base.iterdir() if d.is_dir()):
            if (dossier / "__manifest__.py").is_file():
                trouves.add(dossier.name)
    return trouves


def modules_de_la_base(utilisateur: str, hote: str, base: str) -> dict[str, str]:
    requete = (
        "select name || '|' || state from ir_module_module "
        "where state in ('installed', 'to upgrade', 'to remove')"
    )
    resultat = subprocess.run(
        ["psql", "-h", hote, "-U", utilisateur, "-d", base, "-tAc", requete],
        capture_output=True,
        text=True,
        check=False,
    )
    if resultat.returncode != 0:
        print(f"psql a échoué :\n{resultat.stderr.strip()}")
        sys.exit(2)
    etat: dict[str, str] = {}
    for ligne in resultat.stdout.strip().splitlines():
        nom, _, statut = ligne.partition("|")
        if nom:
            etat[nom] = statut or "installé"
    return etat


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("-d", "--database", default="odoo20")
    analyseur.add_argument("--hote", default="127.0.0.1")
    analyseur.add_argument("--utilisateur", default="odoo")
    options = analyseur.parse_args()

    du_code = modules_du_code()
    de_la_base = modules_de_la_base(options.utilisateur, options.hote, options.database)

    fantomes = sorted(nom for nom in de_la_base if nom not in du_code)
    absents = sorted(nom for nom in NOS_MODULES if nom not in de_la_base)

    print(f"{len(de_la_base)} module(s) dans « {options.database} », {len(du_code)} dans le code.")
    if fantomes:
        print(f"\nFantômes — installés en base, introuvables sur le disque ({len(fantomes)}) :")
        for nom in fantomes:
            print(f"  {nom} ({de_la_base[nom]})")
    if absents:
        # Information, pas défaut : une base de travail n'installe pas forcément
        # les cinq modules — la base neuve, elle, les a tous.
        print(f"\nNos modules absents de cette base ({len(absents)}) :")
        for nom in absents:
            print(f"  {nom}")

    if fantomes:
        return 1
    print("\nAucun fantôme.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
