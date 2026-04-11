#!/bin/bash
# F-025: Apply APP_DB_PASSWORD from the container environment to the
# praxiszeit_app role after init-db-user.sql has created it.
#
# This runs exactly once on first initialization of the PostgreSQL data
# directory (the postgres image executes /docker-entrypoint-initdb.d/*
# in lexical order; .sql runs first, then .sh — hence the ordering here).
#
# Refuses to run with a weak/default password so that operators cannot
# accidentally deploy production with the old username-as-password value.
set -euo pipefail

if [ -z "${APP_DB_PASSWORD:-}" ]; then
    echo "FATAL: APP_DB_PASSWORD must be set in the environment." >&2
    exit 1
fi

# Reject obviously weak values
case "${APP_DB_PASSWORD}" in
    praxiszeit_app|praxiszeit|password|changeme|"")
        echo "FATAL: APP_DB_PASSWORD is weak/default. Generate a random value with: python3 -c 'import secrets;print(secrets.token_hex(24))'" >&2
        exit 1
        ;;
esac

if [ "${#APP_DB_PASSWORD}" -lt 16 ]; then
    echo "FATAL: APP_DB_PASSWORD is shorter than 16 characters." >&2
    exit 1
fi

# Use the superuser from POSTGRES_USER (the default postgres entrypoint
# already runs as this role) to set the app role's password.
psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" <<SQL
ALTER ROLE praxiszeit_app PASSWORD '${APP_DB_PASSWORD//\'/\'\'}';
SQL

echo "Set password for praxiszeit_app"
