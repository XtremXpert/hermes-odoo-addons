#!/bin/bash
# Les garde-fous du cycle de mot de passe applicatif tiennent-ils ?
#
# Aucun reseau, aucun secret : on n'eprouve ici que les refus locaux, ceux qui
# doivent empecher une ecriture accidentelle. Ce qui touche au serveur se verifie
# sur place, avec « etat » ou « liste » — en LECTURE SEULE.
#
#     bash tools/test_app_password.sh

set -u

ICI=$(dirname "$0")
SCRIPT="$ICI/mailcow_app_password.sh"
echecs=0

attendre() {
    local attendu="$1" description="$2"
    shift 2
    local sortie code
    sortie=$(bash "$SCRIPT" "$@" 2>&1)
    code=$?
    if [ "$code" = "$attendu" ]; then
        echo "  ok    : $description (code $code)"
    else
        echo "  ECHEC : $description — code $code, attendu $attendu"
        echo "          sortie : $(echo "$sortie" | head -1 | cut -c1-90)"
        echecs=$((echecs + 1))
    fi
}

echo "Garde-fous du cycle de mot de passe applicatif"
attendre 0 "l'aide sort en succes"             --aide
attendre 2 "aucun mode ne fait rien"           ""
attendre 2 "un mode inconnu se refuse"         danse
attendre 2 "une option inconnue se refuse"     etat --vite
attendre 3 "creer renvoie vers Odoo"            creer une-boite un-nom
attendre 3 "effacer sans --ecrire"             effacer 12
attendre 3 "effacer un identifiant textuel"    effacer abc --ecrire
attendre 3 "effacer un identifiant vide"       effacer "" --ecrire

echo
if [ "$echecs" = "0" ]; then
    echo "Les garde-fous tiennent."
else
    echo "$echecs garde-fou(s) en defaut." >&2
fi
[ "$echecs" = "0" ]
