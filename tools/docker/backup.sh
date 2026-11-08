#!/usr/bin/env bash
# PraxisZeit — Docker-DB-Backup (Plain-SQL-Dump + gzip).
#
# Erwartet, dass es NEBEN der docker-compose.yml + .env liegt (im Docker-Bundle
# der Fall). Sichert die LAUFENDE Datenbank nach ./backups/praxiszeit_<ts>.sql.gz.
#
# VOR einem Versions-Update ausfuehren (DB der Vorversion sichern), danach mit
# restore.sh wieder einspielen. Der Stack muss laufen (docker compose up).
#
# Format: gzip-komprimierter Plain-SQL-Dump (NICHT pg_dump -Fc — das waere doppelt
# komprimiert und liesse sich nicht wie dokumentiert per gunzip|psql einspielen).
set -euo pipefail
# Audit 2026-11-07 S3-06: die Dumps enthalten alle Personal- und Krankheitsdaten
# (Art. 9 DSGVO). Mit der ueblichen umask 022 waeren sie und der Ordner fuer
# jedes lokale Konto des Docker-Hosts lesbar. Ab hier entsteht alles 0600/0700.
umask 077

# Bundle: docker-compose.yml + .env liegen NEBEN diesem Skript. Git-Checkout:
# das Skript liegt in tools/docker/, docker-compose.yml + .env im Repo-Root.
cd "$(dirname "$0")"
if [ ! -f docker-compose.yml ] && [ -f ../../docker-compose.yml ]; then cd ../../; fi

if [ ! -f .env ]; then
    echo "FEHLER: .env nicht gefunden — zuerst 'bash generate-secrets.sh' ausfuehren." >&2
    exit 1
fi

# DB-Name/-User aus der .env lesen (Default = praxiszeit), ohne die ganze .env zu
# sourcen (vermeidet Probleme mit Sonderzeichen in anderen Werten).
PG_USER="$(grep -E '^POSTGRES_USER=' .env | head -1 | cut -d= -f2-)"
PG_DB="$(grep -E '^POSTGRES_DB=' .env | head -1 | cut -d= -f2-)"
PG_USER="${PG_USER:-praxiszeit}"
PG_DB="${PG_DB:-praxiszeit}"

BACKUP_DIR="./backups"
mkdir -p "$BACKUP_DIR"
# Bestand aus aelteren Versionen (0755/0644) nachziehen.
chmod 700 "$BACKUP_DIR"
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'praxiszeit_*.sql.gz' -exec chmod 600 {} +
OUT="${BACKUP_DIR}/praxiszeit_$(date +%Y%m%d_%H%M%S).sql.gz"

echo "Sichere Datenbank '${PG_DB}' (User '${PG_USER}') ..."
if docker compose exec -T db pg_dump -U "$PG_USER" --clean --if-exists "$PG_DB" | gzip > "$OUT"; then
    # Leeren/abgebrochenen Dump erkennen (1.8.12-Lehre): gzip muss intakt sein
    # (-t fängt Trunkierung) UND mehr als ein leeres gzip-Gerüst (~20 Byte) sein.
    # Kein `gzip -dc | head` unter pipefail (SIGPIPE-Footgun, CLAUDE.md) — die
    # komprimierte Größe genügt: ein leeres gzip ist ~20 Byte, ein echter Dump KB+.
    if ! gzip -t "$OUT" 2>/dev/null || [ "$(stat -c%s "$OUT" 2>/dev/null || echo 0)" -le 30 ]; then
        echo "FEHLER: Backup ist leer/ungueltig — wird geloescht." >&2
        rm -f "$OUT"
        exit 1
    fi
    # Signaturzeile anhaengen (Audit 2026-11-07, Fix-Runde S3-03): HMAC mit dem
    # SECRET_KEY des Backend-Containers ueber den entpackten Dump, als zweites
    # gzip-Mitglied (gunzip -c liefert Dump + Kommentarzeile). restore.sh spielt
    # eine Sicherung ohne passende Signatur nur mit --force-unverified ein.
    SIG_TMP="$(mktemp "${BACKUP_DIR}/.signatur.XXXXXX")"
    if gunzip -c "$OUT" | docker compose exec -T backend python -m app.core.backup_mac sign > "$SIG_TMP" \
            && [ -s "$SIG_TMP" ]; then
        gzip -c < "$SIG_TMP" >> "$OUT"
    else
        echo "WARNUNG: Die Sicherung konnte nicht signiert werden (Backend nicht erreichbar" >&2
        echo "oder aeltere Version). restore.sh verlangt fuer sie --force-unverified." >&2
    fi
    rm -f "$SIG_TMP"
    echo "Backup erstellt: ${OUT} ($(du -h "$OUT" | cut -f1))"
else
    echo "FEHLER: Backup fehlgeschlagen." >&2
    rm -f "$OUT"
    exit 1
fi
