#!/usr/bin/env bash
# Lance Odoo 20 en local (bases odoo20 et odoo20_neuve par defaut).
#
# conf/odoo.conf laisse db_host vide : connexion par socket Unix. Ne pas y
# remettre localhost : en TCP, libpq (psycopg2-binary) tente GSSAPI/Kerberos,
# ce qui passe par XPC sur macOS, et macOS tue alors chaque worker forke
# (SIGSEGV dans _os_log_preferences_refresh).
#
# Usage : ./start.sh [options ou sous-commande odoo-bin]
#   ex. ./start.sh -u wazo_phone --stop-after-init
#       ./start.sh --workers 2
#       ./start.sh shell --no-http < script.py
set -euo pipefail

cd "$(dirname "$0")"

export PYTHONPATH=""

has_db=false
for arg in "$@"; do
    case "$arg" in
        -d|-d*|--database|--database=*) has_db=true ;;
    esac
done

args=("$@")
if ! $has_db; then
    # Les deux bases du poste : celle de tous les jours, et la base neuve
    # d'essai. Passer -d pour n'en servir qu'une seule.
    args+=(--database odoo20,odoo20_neuve)
fi

# Les arguments passent AVANT les options fixes. Une sous-commande (« shell »,
# « db », « scaffold »...) doit venir avant les options, sinon odoo-bin la prend
# pour un argument du serveur et refuse : « unrecognized parameters: shell ».
exec .venv/bin/python odoo/odoo-bin "${args[@]}" -c conf/odoo.conf
