#!/usr/bin/env bash
#
# PraxisZeit - Naechtliches Datenbank-Backup
#
# Cronjob einrichten (als root):
#   0 2 * * * /opt/praxiszeit/scripts/backup-db.sh >> /var/log/praxiszeit-backup.log 2>&1
#
set -euo pipefail

BACKUP_DIR="/opt/praxiszeit/backup"
PROJECT_DIR="/opt/praxiszeit"
RETENTION_DAYS=31
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/praxiszeit_${TIMESTAMP}.sql.gz"

# Backup-Verzeichnis anlegen falls noetig
mkdir -p "${BACKUP_DIR}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starte Backup..."

# Dump erstellen und komprimieren
if docker compose -f "${PROJECT_DIR}/docker-compose.yml" exec -T db \
    pg_dump -U praxiszeit --clean --if-exists praxiszeit \
    | gzip > "${BACKUP_FILE}"; then

    SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup erstellt: ${BACKUP_FILE} (${SIZE})"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FEHLER: Backup fehlgeschlagen!" >&2
    rm -f "${BACKUP_FILE}"
    exit 1
fi

# Alte Backups loeschen (aelter als RETENTION_DAYS Tage)
DELETED=$(find "${BACKUP_DIR}" -name "praxiszeit_*.sql.gz" -type f -mtime +${RETENTION_DAYS} -print -delete | wc -l)
if [ "${DELETED}" -gt 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ${DELETED} alte Backup(s) geloescht (aelter als ${RETENTION_DAYS} Tage)"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Fertig."
