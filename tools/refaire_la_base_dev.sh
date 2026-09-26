#!/bin/bash
# Rejouer la base de developpement, puis reimporter la configuration Mailcow.
#
# Trois choses, dans cet ordre, et jamais dans un autre :
#   1. sauvegarder la base courante, HORS du depot (le depot est privé — on n'y met rien de secret par principe, et les
#      parametres systeme portent la cle de l'API Mailcow) ;
#   2. batir une base neuve et y installer les cinq modules ;
#   3. reimporter de Mailcow les domaines, boites et alias, pour que la base
#      neuve ne reste pas vide alors que le serveur de courriel, lui, est plein.
#
# Usage :
#   bash tools/refaire_la_base_dev.sh --simuler     # montre tout, ne touche a rien
#   bash tools/refaire_la_base_dev.sh              # demande confirmation, puis agit
#
# Ce qu'il refuse : tourner pendant qu'Odoo tourne, ecrire une sauvegarde dans le
# depot, et afficher la valeur d'un parametre systeme (il n'en montre que le nom).
#
# La reprise de la configuration est indispensable : la synchronisation appelle
# l'API Mailcow, qui exige « mailcow.api_key ». Sans la cle reportee, la base
# neuve serait muette — et le message d'erreur parlerait d'authentification, pas
# de la vraie cause.

set -u

RACINE="$(cd "$(dirname "$0")/.." && pwd)"
COURANTE=${COURANTE:-odoo20}
NEUVE=${NEUVE:-odoo20_neuve}
SAUVEGARDES=${SAUVEGARDES:-$HOME/.hermes/sauvegardes}
MODULES="asterisk_ari,mailcow_admin,voipms_sms,wazo_phone,wazo_server"
SIMULER=0
for a in "$@"; do [ "$a" = "--simuler" ] && SIMULER=1; done

dire() { printf '  %s\n' "$*"; }
refuser() { printf 'REFUS : %s\n' "$*" >&2; exit 3; }

# --- 0. les garde-fous -------------------------------------------------------
[ -f "$RACINE/conf/odoo.conf" ] || refuser "conf/odoo.conf introuvable : lance depuis la racine du depot"

# Odoo doit etre arrete : on ne renomme pas une base sous un serveur qui la sert.
if pgrep -f "odoo-bin.*-c conf/odoo.conf" > /dev/null; then
    if [ "$SIMULER" = "1" ]; then
        dire "AVERTISSEMENT : Odoo tourne. En vrai, la bascule s'arreterait ici."
        dire "                pour l'arreter : pkill -f \"odoo-bin.*-c conf/odoo.conf\""
    else
        refuser "Odoo tourne encore. L'arreter d'abord :
    pkill -f \"odoo-bin.*-c conf/odoo.conf\""
    fi
fi

# La sauvegarde doit sortir du depot : il est privé — on n'y met rien de secret par principe, et les parametres portent
# la cle de l'API. Un chemin sous la racine du depot est refuse.
case "$SAUVEGARDES" in
    "$RACINE"|"$RACINE"/*) refuser "« $SAUVEGARDES » est DANS le depot : choisir un dossier hors du depot" ;;
esac

case "$COURANTE$NEUVE" in
    *[!A-Za-z0-9_]*) refuser "les noms de base ne doivent porter que lettres, chiffres et soulignes" ;;
esac

HORODATE=$(date +%Y%m%d-%H%M)
DUMP="$SAUVEGARDES/$COURANTE-$HORODATE.dump"
REGLAGES="$SAUVEGARDES/$COURANTE-$HORODATE-reglages.json"

# --- 1. la sauvegarde --------------------------------------------------------
dire "1. sauvegarde de $COURANTE"
dire "   fichier : $DUMP (hors du depot, droits 600)"
dire "   reglages : $REGLAGES (noms et valeurs, droits 600 — la cle est dedans)"

# « db_host » est vide dans conf/odoo.conf : PostgreSQL est joint par la socket
# Unix, ce qui evite la negociation GSSAPI que macOS tue au premier fork.
sql() { psql -d "$1" -tAc "$2"; }

if [ "$SIMULER" = "1" ]; then
    dire "   [simule] mkdir -p $SAUVEGARDES && chmod 700 $SAUVEGARDES"
    dire "   [simule] pg_dump -Fc $COURANTE > $DUMP && chmod 600 $DUMP"
    dire "   [simule] reglages : SELECT name, value FROM ir_config_parameter (vers $REGLAGES)"
else
    mkdir -p "$SAUVEGARDES" || refuser "impossible de creer $SAUVEGARDES"
    chmod 700 "$SAUVEGARDES"
    if ! pg_dump -Fc "$COURANTE" > "$DUMP"; then
        refuser "pg_dump a echoue (voir le message ci-dessus)"
    fi
    chmod 600 "$DUMP"
    # On exporte les parametres : ce sont eux qui portent la cle de l'API.
    # Le contenu n'est jamais affiche, seulement consigne.
    if ! psql -d "$COURANTE" -tAc "COPY (SELECT name, value FROM ir_config_parameter) TO STDOUT" \
         > "$REGLAGES"; then
        refuser "l'export des reglages a echoue"
    fi
    chmod 600 "$REGLAGES"
    dire "   sauvegarde faite : $(du -h "$DUMP" | cut -f1), $(wc -l < "$REGLAGES" | tr -d ' ') reglages"
fi

# --- 2. la base neuve --------------------------------------------------------
dire "2. base neuve : $NEUVE, avec les cinq modules"
if [ "$SIMULER" = "1" ]; then
    dire "   [simule] dropdb --if-exists --force $NEUVE && createdb $NEUVE"
    dire "   [simule] ./start.sh --database $NEUVE -i $MODULES --stop-after-init"
else
    if ! dropdb --if-exists --force "$NEUVE"; then
        refuser "dropdb a echoue (voir le message ci-dessus)"
    fi
    createdb "$NEUVE" || refuser "createdb a echoue"
    # Le seul lanceur autorise : ./start.sh
    if ! ./start.sh --database "$NEUVE" -i "$MODULES" --stop-after-init; then
        refuser "l'installation des modules a echoue (voir le journal)"
    fi
fi

# --- 3. le reimport Mailcow --------------------------------------------------
dire "3. reimport de la configuration Mailcow dans $NEUVE"
dire "   (domaines, boites, alias — c'est la synchronisation du module)"

# Le gabarit doit TERMINER par « XXXXXX » : sur macOS, mktemp refuse un suffixe
# place apres les X, echoue, et le fichier n'existe pas.
SONDE=$(mktemp "${TMPDIR:-/tmp}/reimport-mailcow-XXXXXX")
cat > "$SONDE" <<'PY'
# Les trois synchronisations du module, dans l'ordre : les domaines d'abord,
# puis ce qui en depend. Chacune interroge l'API Mailcow et s'appelle SANS fiche
# locale — c'est ainsi que le module amorce une base vide, comme le dit sa
# docstring. Exiger des fiches existantes serait passer a cote du seul cas qui
# nous interesse.
for modele in ("mailcow.domain", "mailcow.mailbox", "mailcow.alias"):
    avant = len(env[modele].with_context(active_test=False).search([]))
    apercu = env[modele]._sync_all_from_mailcow(dry_run=True)
    # « apercu » liste les CHANGEMENTS que la synchronisation appliquerait, pas
    # les objets du serveur : zero veut dire « deja en phase », pas « rien vu ».
    print(f"{modele} : {avant} fiche(s) locale(s), {len(apercu)} changement(s) a appliquer")
    env[modele]._sync_all_from_mailcow()
    env.cr.commit()
    apres = len(env[modele].with_context(active_test=False).search([]))
    print(f"{modele} : {apres} fiche(s) apres synchronisation")
PY

if [ "$SIMULER" = "1" ]; then
    dire "   [simule] ./start.sh shell --no-http < $SONDE"
    dire "   [simule] la sonde contient :"
    sed 's/^/     /' "$SONDE"
    rm -f "$SONDE"
else
    # Sous-commande AVANT les options, comme l'ecrit l'en-tete de start.sh :
    # sinon odoo-bin prend « shell » pour un argument du serveur et refuse
    # (mesure : « -d/--database/db_name has multiple database » puis code 2).
    if ! ./start.sh shell --no-http --database "$NEUVE" < "$SONDE"; then
        rm -f "$SONDE"
        refuser "la synchronisation a echoue : la cle de l'API a-t-elle ete reportee depuis $REGLAGES ?"
    fi
    rm -f "$SONDE"
fi

dire
dire "Termine. Base neuve : $NEUVE"
dire "Rappel : la cle de l'API est dans $REGLAGES (droits 600) — à reporter dans"
dire "ir_config_parameter si la synchronisation a echoue par authentification."
