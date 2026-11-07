#!/bin/sh
# Start des Backend-Containers (CMD im Dockerfile).
#
# 1. Migrationen mit der Superuser-Verbindung DATABASE_URL_MIGRATIONS.
# 2. Nur lesende Rolle praxiszeit_backup fuer die Datensicherung der
#    Weboberflaeche einrichten (Passwort je Start neu) -> DATABASE_URL_BACKUP.
# 3. uvicorn OHNE DATABASE_URL_MIGRATIONS starten (Audit 2026-11-07 S3-13,
#    Fix-Runde): eine Code-Ausfuehrung oder ein Umgebungs-Leck im Webprozess
#    hiesse sonst Superuser - RLS wirkungslos, COPY ... TO PROGRAM moeglich.
#    Wie nativ (praxiszeit-server.py uvicorn_start).
set -e
alembic upgrade head
if DATABASE_URL_BACKUP="$(python -m app.core.backup_role)"; then
    export DATABASE_URL_BACKUP
else
    unset DATABASE_URL_BACKUP
fi
exec env -u DATABASE_URL_MIGRATIONS uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips='172.16.0.0/12,10.0.0.0/8,192.168.0.0/16'
