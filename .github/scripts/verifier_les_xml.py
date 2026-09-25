"""Vérifier que chaque XML versionné est bien formé.

Un fichier XML mal formé fait échouer le chargement du module entier, et
souvent loin de sa cause. Le vérifier ici coûte une seconde.
"""
import subprocess
import sys
import xml.etree.ElementTree as ET


def main():
    liste = subprocess.run(['git', 'ls-files', '*.xml'], capture_output=True,
                           text=True, check=True).stdout.split()
    en_erreur = []
    for chemin in liste:
        try:
            ET.parse(chemin)
        except ET.ParseError as erreur:
            en_erreur.append('%s : %s' % (chemin, erreur))
    print('%d fichier(s) XML vérifié(s), %d en erreur' % (len(liste), len(en_erreur)))
    if en_erreur:
        print('\n'.join(en_erreur))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
