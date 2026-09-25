#!/usr/bin/env bash
# Lance Odoo 20 en local (base odoo20 par defaut).
#
# PGGSSENCMODE=disable : sur macOS, libpq (psycopg2-binary) tente GSSAPI/Kerberos
# a chaque connexion, ce qui passe par XPC. Dans un processus enfant issu d'un
# fork() sans exec() (workers Odoo, multiprocessing), macOS tue alors le
# processus (SIGSEGV dans _os_log_preferences_refresh).
#
# Usage : ./start.sh [options ou sous-commande odoo-bin]
#   ex. ./start.sh -u wazo_phone --stop-after-init
#       ./start.sh --workers 2
#       ./start.sh shell --no-http < script.py
set -euo pipefail

cd "$(dirname "$0")"

export PGGSSENCMODE=disable
export PYTHONPATH=""

has_db=false
for arg in "$@"; do
    case "$arg" in
        -d|-d*|--database|--database=*) has_db=true ;;
    esac
done

args=("$@")
if ! $has_db; then
    args+=(--database odoo20)
fi

# Les arguments passent AVANT les options fixes. Une sous-commande (« shell »,
# « db », « scaffold »...) doit venir avant les options, sinon odoo-bin la prend
# pour un argument du serveur et refuse : « unrecognized parameters: shell ».
exec .venv/bin/python odoo/odoo-bin "${args[@]}" -c conf/odoo.conf
