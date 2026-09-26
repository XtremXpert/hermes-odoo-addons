#!/usr/bin/env python3
"""Consigne la révision d'Odoo contre laquelle ce dépôt a été validé.

`odoo/`, `design-themes/` et `enterprise/` sont des clones simples, ignorés par
git : rien dans le dépôt ne dit quelle révision a réellement été éprouvée. Ce
fichier l'écrit, et `check` dit si l'arbre local a dérivé depuis.

    python3 tools/odoo_lock.py write      # relever l'état actuel
    python3 tools/odoo_lock.py check      # comparer l'arbre au fichier
    python3 tools/odoo_lock.py remettre   # remettre chaque arbre sur sa révision
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
VERROU = RACINE / "odoo.lock"
ARBRES = ("odoo", "design-themes", "enterprise")


def git(arbre: str, *arguments: str) -> str:
    resultat = subprocess.run(
        ["git", "-C", str(RACINE / arbre), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    return resultat.stdout.strip()


def relever() -> dict[str, dict[str, str]]:
    """L'état actuel de chaque arbre — source, branche, révision."""
    etat: dict[str, dict[str, str]] = {}
    for arbre in ARBRES:
        if not (RACINE / arbre / ".git").exists():
            continue
        etat[arbre] = {
            "source": git(arbre, "remote", "get-url", "origin"),
            "branche": git(arbre, "rev-parse", "--abbrev-ref", "HEAD"),
            "commit": git(arbre, "rev-parse", "HEAD"),
        }
    return etat


def lire() -> dict[str, dict[str, str]]:
    if not VERROU.exists():
        return {}
    etat: dict[str, dict[str, str]] = {}
    courant: str | None = None
    for ligne in VERROU.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("#") or not ligne.strip():
            continue
        if not ligne.startswith(" "):
            courant = ligne.rstrip(":").strip()
            etat[courant] = {}
        elif courant:
            cle, _, valeur = ligne.strip().partition(": ")
            etat[courant][cle] = valeur
    return etat


def ecrire() -> int:
    etat = relever()
    if not etat:
        print("Aucun arbre à consigner (odoo/, design-themes/, enterprise/ absents).")
        return 1
    lignes = [
        "# Révisions contre lesquelles ce dépôt a été éprouvé.",
        "# Relever : python3 tools/odoo_lock.py write",
        "# Comparer : python3 tools/odoo_lock.py check",
        "",
    ]
    for arbre, infos in etat.items():
        lignes.append(f"{arbre}:")
        for cle in ("source", "branche", "commit"):
            lignes.append(f"  {cle}: {infos.get(cle, '')}")
    VERROU.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print(f"{VERROU.name} écrit pour {len(etat)} arbre(s) :")
    for arbre, infos in etat.items():
        print(f"  {arbre} {infos['commit'][:12]} ({infos['branche']})")
    return 0


def verifier() -> int:
    attendu, actuel = lire(), relever()
    if not attendu:
        print("odoo.lock absent : lancer d'abord « python3 tools/odoo_lock.py write ».")
        return 1
    ecarts = 0
    for arbre, infos in attendu.items():
        if arbre not in actuel:
            # Normal hors du poste de travail : la CI ne clone que odoo/.
            print(f"  {arbre} : dans le verrou, absent ici (non cloné)")
            continue
        if actuel[arbre]["commit"] != infos.get("commit"):
            print(
                f"  {arbre} : {actuel[arbre]['commit'][:12]} sur le disque, "
                f"{infos.get('commit', '?')[:12]} dans le verrou"
            )
            ecarts += 1
    if ecarts:
        print(f"{ecarts} arbre(s) ont dérivé — vérifier que la suite passe toujours.")
        return 1
    print(f"Les {len(attendu)} arbres sont sur la révision consignée.")
    return 0


def remettre() -> int:
    attendu = lire()
    if not attendu:
        print("odoo.lock absent : rien à remettre.")
        return 1
    for arbre, infos in attendu.items():
        commit = infos.get("commit")
        if not commit or not (RACINE / arbre / ".git").exists():
            continue
        subprocess.run(
            ["git", "-C", str(RACINE / arbre), "checkout", "--quiet", commit], check=False
        )
        print(f"  {arbre} -> {commit[:12]}")
    return 0


def main() -> int:
    quoi = sys.argv[1] if len(sys.argv) > 1 else "check"
    if quoi == "write":
        return ecrire()
    if quoi == "check":
        return verifier()
    if quoi == "remettre":
        return remettre()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
