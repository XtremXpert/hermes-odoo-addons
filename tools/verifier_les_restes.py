#!/usr/bin/env python3
"""Vérifie ce qu'un module Odoo ne dit pas tout seul.

Trois contrôles, chacun pour un défaut qui passe la relecture :

1. la version du manifeste suit la série du dépôt (`20.0.x.y.z`) ;
2. chaque modèle déclaré a une règle d'accès dans les CSV du module — sans
   elle, seul le superutilisateur peut s'en servir, et rien ne le signale ;
3. chaque import `@addon/chemin` du JavaScript existe vraiment.

Usage :
    python3 tools/verifier_les_restes.py        # résumé
    python3 tools/verifier_les_restes.py -v     # en nommant chaque fichier
"""

# Outil en ligne de commande, lancé hors d'Odoo : il parle à son terminal,
# « print » est sa sortie, pas un journal.
# pylint: disable=print-used

from __future__ import annotations

import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SERIE = "20.0"
MODULES = (
    "asterisk_ari",
    "mailcow",
    "mailcow_server",
    "mailcow_tenant",
    "voipms_sms",
    "wazo_phone",
    "wazo_server",
    "wazo_tenant",
    "wazo_voipms",
)
# Disposition OCA : les modules sont à la racine du dépôt.
DOSSIER_MODULES = RACINE

# Les racines d'addons, en relatif : portable d'un poste à l'autre.
RACINES_ADDONS = ("odoo/addons", "odoo/odoo/addons", "design-themes", ".")
# Les mêmes, moins le dépôt lui-même : ce sont elles qui doivent exister pour
# qu'un import Odoo soit vérifiable. Le travail « Qualité » de la CI ne clone
# pas Odoo ; là-bas, ce contrôle n'a rien à inspecter et doit le dire.
ARBRES_ODOO = ("odoo/addons", "odoo/odoo/addons", "design-themes")

# La série, en forme courte (« 20.0.3 ») ou longue (« 20.0.3.0.0 », celle de l'OCA,
# qu'exige pylint-odoo). En 20.0, la forme longue se nomme aussi en dossier de
# migration : « 20.0. » est un préfixe de série, suivi de trois nombres. Ce n'était pas
# le cas en 19.5, qui n'est pas un préfixe de série : là, un manifeste à cinq segments
# ne pouvait être égalé par aucun nom de dossier, et le script ne s'exécutait jamais.
VERSION_ATTENDUE = re.compile(rf"^{re.escape(SERIE)}(\.\d+){{1,3}}$")

# Ce qu'Odoo accepte comme nom de dossier dans « migrations/ » : deux ou trois nombres,
# éventuellement précédés d'un préfixe de série de la forme « 19.0. ». C'est le VERSION_RE
# de odoo/modules/migration.py, recopié tel quel — l'ancrage compte, il compare le nom
# entier. Une version comme « 19.5.2.0.0 » n'est nommable par aucun dossier, mais Odoo ne
# s'en plaint que si le dossier existe et qu'il est refusé.
NOM_DE_DOSSIER = re.compile(
    r"^((6\.1|[6-9]\.0|[1-9]\d+\.0|(7|8|9|10)\.saas~[1-9]\d*|saas~(1[1-9]|[2-9]\d+)\.[1-9])\.)?"
    r"\d+\.\d+(\.\d+)?$"
)
CLASSE_MODELE = re.compile(r"^class\s+\w+\(\s*models\.(\w+)\s*\)", re.M)
NOM_MODELE = re.compile(r"^\s+_name\s*=\s*['\"]([\w.]+)['\"]", re.M)
HERITAGE = re.compile(r"^\s+_inherit\s*=", re.M)
IMPORT_JS = re.compile(r"""from\s+["']@([\w.]+)/([^"']+)["']""")


def lire_manifeste(module: str) -> str | None:
    chemin = DOSSIER_MODULES / module / "__manifest__.py"
    return chemin.read_text(encoding="utf-8") if chemin.exists() else None


def modeles_du_module(module: str, verbeux: bool) -> list[tuple[str, str]]:
    """Les modèles NOUVEAUX du module : `_name` sans `_inherit` à côté."""
    trouves: list[tuple[str, str]] = []
    dossier = DOSSIER_MODULES / module
    # Les assistants (TransientModel) vivent dans « wizards/ », à la manière de l'OCA :
    # ils ont besoin d'une règle d'accès tout autant que les modèles.
    fichiers = sorted(dossier.glob("models/*.py")) + sorted(dossier.glob("wizards/*.py"))
    for fichier in fichiers:
        source = fichier.read_text(encoding="utf-8")
        for bloc in re.split(r"(?=^class\s)", source, flags=re.M):
            base = CLASSE_MODELE.search(bloc)
            if not base or base.group(1) == "AbstractModel":
                # Un modèle abstrait ne stocke rien : il n'a pas de règle d'accès.
                continue
            nom = NOM_MODELE.search(bloc)
            if nom and not HERITAGE.search(bloc):
                trouves.append((nom.group(1), fichier.name))
    return trouves


def modeles_couverts(module: str) -> set[str]:
    """Ce que les CSV de sécurité du module déclarent, tous fichiers confondus."""
    couverts: set[str] = set()
    for csv in sorted((DOSSIER_MODULES / module / "security").glob("*.csv")):
        for ligne in csv.read_text(encoding="utf-8").splitlines()[1:]:
            colonnes = [c.strip().strip('"') for c in ligne.split(",")]
            if len(colonnes) < 3 or not colonnes[2]:
                continue
            # Deux façons d'écrire le modèle : son nom (« mailcow.domain »), ou
            # l'identifiant externe de sa fiche (« model_mailcow_domain »).
            brut = colonnes[2]
            if brut.startswith("model_"):
                couverts.add(brut[len("model_") :].replace("_", "."))
            else:
                couverts.add(brut)
    return couverts


# Les paquets du bundler, pas des fichiers : « @odoo/owl » est le paquet OWL
# livré avec web, il n'a aucun chemin à résoudre.
PAQUETS = {"odoo"}


def import_resolu(addon: str, chemin: str) -> bool:
    if addon in PAQUETS:
        return True
    for racine in RACINES_ADDONS:
        base = RACINE / racine / addon / "static" / "src" / chemin
        # « Path(…).with_suffix » remplacerait le « .esm » d'un « x.esm » : on ajoute.
        for candidat in (base, Path(f"{base}.js"), base / "index.js"):
            if candidat.is_file():
                return True
    return False


def defaut_de_forme(dossier_module: Path) -> str | None:
    """Les fichiers de règles de « security/ » sont-ils lisibles sans surprise ?

    Deux pièges concrets. Un fichier qui ne finit pas par un retour à la ligne
    avale la règle qu'on ajoute par « >> » : elle se colle à la précédente et le
    nombre de champs ne veut plus rien dire. Et une ligne dont le nombre de
    champs diffère de l'en-tête est lue de travers à l'installation du module.
    """
    import csv

    for fichier in sorted((dossier_module / "security").glob("*.csv")):
        contenu = fichier.read_text()
        if contenu and not contenu.endswith("\n"):
            relatif = fichier.relative_to(RACINE)
            return f"{relatif} : la dernière ligne n'est pas terminée"
        lignes = [ligne for ligne in contenu.splitlines() if ligne.strip()]
        if not lignes:
            continue
        largeur = len(next(csv.reader([lignes[0]])))
        for numero, ligne in enumerate(lignes[1:], start=2):
            nombre = len(next(csv.reader([ligne])))
            if nombre != largeur:
                relatif = fichier.relative_to(RACINE)
                return f"{relatif} : ligne {numero}, {nombre} champs au lieu de {largeur}"
    return None


def main() -> int:
    verbeux = "-v" in sys.argv or "--verbeux" in sys.argv
    defauts: list[str] = []
    # Un arbre Odoo est-il là ? Sans lui, un import « @web/… » n'est pas
    # vérifiable — et le déclarer mort serait un faux positif.
    arbres_odoo = any((RACINE / racine).is_dir() for racine in ARBRES_ODOO)
    if not arbres_odoo:
        print("Arbre Odoo absent : les imports JavaScript ne sont pas vérifiés.")

    for module in MODULES:
        manifeste = lire_manifeste(module)
        if manifeste is None:
            defauts.append(f"{module} : __manifest__.py absent")
            continue

        # 1. la version
        version = re.search(r"['\"]version['\"]\s*:\s*['\"]([^'\"]+)['\"]", manifeste)
        valeur = version.group(1) if version else ""
        if not version:
            defauts.append(f"{module} : aucune version dans le manifeste")
        elif not VERSION_ATTENDUE.match(valeur):
            defauts.append(f"{module} : version « {valeur} » hors série (attendu {SERIE}.x.y.z)")

        # 1 bis. un module qui porte des scripts de migration doit pouvoir les nommer.
        a_des_scripts = (DOSSIER_MODULES / module / "migrations").is_dir()
        if valeur and a_des_scripts and not NOM_DE_DOSSIER.match(valeur):
            defauts.append(
                f"{module} : porte des scripts de migration, mais sa version "
                f"« {valeur} » ne peut être nommée par aucun dossier"
            )

        # 1 ter. la forme des fichiers de règles, avant de lire ce qu'ils couvrent.
        forme = defaut_de_forme(DOSSIER_MODULES / module)
        if forme:
            defauts.append(f"{module} : {forme}")

        # 2. les règles d'accès
        couverts = modeles_couverts(module)
        for nom, fichier in modeles_du_module(module, verbeux):
            if nom not in couverts:
                defauts.append(
                    f"{module} : le modèle {nom} ({fichier}) n'a aucune règle "
                    f"d'accès dans security/"
                )

        # 3. les imports JavaScript — seulement si un arbre Odoo est là pour les
        #    résoudre. Le travail « Qualité » de la CI ne clone pas Odoo : sans
        #    cette garde, tous les imports « @web/… » y passeraient pour morts.
        if not arbres_odoo:
            continue
        imports: set[tuple[str, str]] = set()
        for js in sorted((DOSSIER_MODULES / module / "static").rglob("*.js")):
            imports |= set(IMPORT_JS.findall(js.read_text(encoding="utf-8")))
        for addon, chemin in sorted(imports):
            if not import_resolu(addon, chemin):
                defauts.append(f"{module} : import « @{addon}/{chemin} » introuvable")

    if defauts:
        print(f"{len(defauts)} défaut(s) :")
        for defaut in defauts:
            print(f"  - {defaut}")
        return 1

    print(f"Aucun défaut sur {len(MODULES)} module(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
