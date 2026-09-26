#!/bin/bash
# Cycle de vie d'un mot de passe applicatif Mailcow.
#
# Ce script est fait pour tourner SUR l'hote de courriel : il pilote le conteneur
# mysql par « docker exec », si bien que le mot de passe de la base ne quitte
# jamais le conteneur et n'apparait ni ici, ni dans un « ps », ni dans un journal.
#
#     ssh bvezina@mail.diverse-cite.com "sudo -n pct exec 30001 -- bash -s -- etat" \
#         < tools/mailcow_app_password.sh
#
# Ou, sur place : bash tools/mailcow_app_password.sh etat
#
# Ce qu'il ne fait jamais :
#   - imprimer le contenu de « password » : seulement sa longueur, masque ;
#   - ecrire sans « --ecrire », ni hors du domaine jetable sans « --j-assume » ;
#   - effacer plusieurs lignes : « effacer » exige UN identifiant numerique ;
#   - avaler une erreur : un echec de mysql est montre et remonte le code de sortie.
#
# MODES
#   etat                    lecture : combien de mots de passe, et leur squelette
#   liste [domaine]         lecture : les lignes, sans le secret
#   verifier <id>           lecture : cette ligne existe-t-elle, est-elle active
#   effacer <id>            ecriture (SQL) : supprime CETTE ligne
#
# La CREATION n'est pas ici : elle appartient a Odoo, qui detient la cle de
# l'API et sait appeler « POST /add/app-passwd » par son assistant. Ce script
# reprend ensuite la main, sur la machine de courriel ou la cle n'a rien a faire.
#
# OPTIONS
#   --ecrire                autorise les modes d'ecriture (sans lui, ils refusent)
#   --domaine <d>           domaine vise (defaut : le jetable test636)
#   --j-assume              accepte un domaine NON jetable (affiche un avertissement)
#   --simuler               montre le SQL sans l'executer
#   --aide                  ce texte

set -u

JETABLE=${JETABLE:-test636.diverse-cite.com}
DOMAINE="$JETABLE"
ECRIRE=0
ASSUME=0
SIMULER=${SIMULER:-0}

# --- arguments ---------------------------------------------------------------
POS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --aide|-h|--help)
            sed -n '2,34p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        --ecrire)   ECRIRE=1; shift ;;
        --j-assume) ASSUME=1; shift ;;
        --simuler)  SIMULER=1; shift ;;
        --domaine)  DOMAINE="${2:-}"; shift 2 ;;
        -*)         echo "option inconnue : $1 (« --aide » pour la liste)" >&2; exit 2 ;;
        *)          POS+=("$1"); shift ;;
    esac
done

MODE="${POS[0]:-}"

# Un mode inconnu doit se refuser, pas tomber dans le vide : la premiere version
# sortait en code 0 sur une faute de frappe, ce qui est le pire des verdicts.
case "$MODE" in
    ""|etat|liste|verifier|creer|effacer) ;;
    *) echo "mode inconnu : « $MODE » (« --aide » pour la liste)" >&2; exit 2 ;;
esac
ARG1="${POS[1]:-}"
ARG2="${POS[2]:-}"

[ -n "$MODE" ] || { echo "Aucun mode. « --aide » pour la liste." >&2; exit 2; }

# --- garde-fous --------------------------------------------------------------
refuser() { echo "REFUS : $*" >&2; exit 3; }
est_jetable() { [ "$DOMAINE" = "$JETABLE" ]; }

# --- transport ---------------------------------------------------------------
# Une seule porte vers l'exterieur. Le SQL voyage par l'ENTREE STANDARD : il ne
# traverse donc aucune couche de guillemets. C'est ce qui manquait a la premiere
# version, ou « COUNT(*) » arrivait au shell du conteneur nu, et cassait.
MYSQL=""
decouvrir_mysql() {
    [ -n "$MYSQL" ] && return 0
    MYSQL=$(docker ps --format '{{.Names}}' | grep -i mysql | head -1)
    [ -n "$MYSQL" ] || refuser "aucun conteneur mysql trouve sur cet hote"
}

# SQL <requete> : rend les lignes brutes (mode -N), montre l'erreur, remonte le code.
SQL() {
    local requete="$1"
    if [ "$SIMULER" = "1" ]; then
        echo "    [simule] $requete"
        return 0
    fi
    decouvrir_mysql
    if ! printf '%s\n' "$requete" | docker exec -i -e "BASE=mailcow" "$MYSQL" \
        sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N "$BASE"'; then
        echo "ECHEC mysql (voir le message de MariaDB ci-dessus)" >&2
        return 1
    fi
}

# --- lecture -----------------------------------------------------------------
COLONNES='id, name, mailbox, domain, LENGTH(password), active,
          CONCAT(imap_access,smtp_access,dav_access,eas_access,pop3_access,sieve_access)'

entete() { echo "  id | nom | boite | domaine | longueur du secret | actif | protocoles"; }

lignes() { SQL "SELECT $COLONNES FROM app_passwd ${1:-} ORDER BY id"; }

etat() {
    local total
    total=$(SQL "SELECT COUNT(*) FROM app_passwd") || exit 1
    total=${total//[[:space:]]/}
    echo "mots de passe applicatifs : $total"
    [ "$total" = "0" ] && return 0
    entete
    lignes | sed 's/^/  /'
}

vide() { [ -z "${1//[[:space:]]/}" ]; }

# --- modes -------------------------------------------------------------------
case "$MODE" in
    etat)
        etat
        ;;

    liste)
        if [ -n "$ARG1" ]; then
            entete; lignes "WHERE domain = '$ARG1'" | sed 's/^/  /'
        else
            entete; lignes | sed 's/^/  /'
        fi
        ;;

    verifier)
        [ -n "$ARG1" ] || refuser "« verifier » attend un identifiant"
        ligne=$(SQL "SELECT $COLONNES FROM app_passwd WHERE id = $ARG1") || exit 1
        if vide "$ligne"; then
            echo "aucune ligne d'identifiant $ARG1"
            exit 4
        fi
        entete
        echo "$ligne" | sed 's/^/  /'
        # Une seconde lecture, par un autre chemin que la premiere : le nom seul.
        nom=$(SQL "SELECT name FROM app_passwd WHERE id = $ARG1") || exit 1
        echo "  seconde lecture du nom : ${nom:-rien}"
        ;;

    creer)
        # Retire, et pas par paresse : la creation appartient a Odoo, qui detient
        # deja la cle et sait appeler POST /add/app-passwd (l'assistant
        # « mailcow.app.password.wizard », avec son test). La refaire ici
        # dupliquerait la capacite et exigerait la cle sur l'hote de courriel.
        refuser "« creer » a ete retire : creer depuis Odoo (assistant « Mot de passe applicatif »), puis verifier et effacer ici"
        ;;

    effacer)
        [ "$ECRIRE" = "1" ] || refuser "« effacer » ecrit : ajouter « --ecrire »"
        [ -n "$ARG1" ] || refuser "« effacer » attend UN identifiant (jamais un domaine)"
        case "$ARG1" in
            *[!0-9]*) refuser "l'identifiant doit etre un nombre : « $ARG1 »" ;;
        esac
        avant=$(SQL "SELECT $COLONNES FROM app_passwd WHERE id = $ARG1") || exit 1
        vide "$avant" && { echo "rien a effacer : aucune ligne $ARG1"; exit 4; }
        echo "ligne qui sera supprimee :"
        entete
        echo "$avant" | sed 's/^/  /'
        domaine_ligne=$(echo "$avant" | cut -f4 | tr -d '[:space:]')
        if [ "$domaine_ligne" != "$JETABLE" ] && [ "$ASSUME" != "1" ]; then
            refuser "$domaine_ligne n'est pas le domaine jetable ($JETABLE) : ajouter « --j-assume »"
        fi
        SQL "DELETE FROM app_passwd WHERE id = $ARG1" || exit 1
        apres=$(SQL "SELECT COUNT(*) FROM app_passwd WHERE id = $ARG1") || exit 1
        apres=${apres//[[:space:]]/}
        if [ "$apres" = "0" ]; then
            echo "efface : la ligne $ARG1 n'existe plus."
        else
            echo "INATTENDU : la ligne $ARG1 est encore la." >&2
            exit 1
        fi
        ;;
esac
