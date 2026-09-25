#!/usr/bin/env bash
# Lance Odoo 20 en local (base odoo20 par defaut).
#
# PGGSSENCMODE=disable : sur macOS, libpq (psycopg2-binary) tente GSSAPI/Kerberos
# a chaque connexion, ce qui passe par XPC. Dans un processus enfant issu d'un
# fork() sans exec() (workers Odoo, multiprocessing), macOS tue alors le
# processus (SIGSEGV dans _os_log_preferences_refresh).
#
# Usage : ./start.sh [options odoo-bin supplementaires]
#   ex. ./start.sh -u wazo_phone --stop-after-init
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

if $has_db; then
    exec .venv/bin/python odoo/odoo-bin -c conf/odoo.conf "$@"
else
    exec .venv/bin/python odoo/odoo-bin -c conf/odoo.conf --database odoo20 "$@"
fi
