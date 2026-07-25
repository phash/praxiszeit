#!/usr/bin/env bash
# PraxisZeit — erzeugt eine .env mit zufaelligen Secrets fuer das Docker-Deployment.
#
# Erwartet, dass es NEBEN der docker-compose.yml + .env.example liegt
# (im Docker-Bundle der Fall; aus dem Quellcode: aus dem Repo-Root aufrufen).
#
# Setzt zufaellige Werte fuer SECRET_KEY, DB-Passwoerter und das Grafana-Passwort,
# ein zufaelliges (komplexes) initiales Admin-Passwort und ENVIRONMENT=production.
set -euo pipefail

cd "$(dirname "$0")"

# Release-Review 1.16.0: Im Docker-Bundle liegt das Skript neben der .env.example,
# im Quellcode-Repo aber unter tools/docker/ — die .env.example nur im Root. Der
# in INSTALL-DOCKER.md und INSTALLATION.md dokumentierte Aufruf
# `bash tools/docker/generate-secrets.sh` brach dadurch IMMER mit
# "FEHLER: .env.example nicht gefunden" ab. Gleicher Fallback wie in
# backup.sh/restore.sh, damit die .env im Root landet (dort sucht compose sie).
if [ ! -f .env.example ] && [ -f ../../.env.example ]; then cd ../../; fi

if [ ! -f .env.example ]; then
    echo "FEHLER: .env.example nicht gefunden. Dieses Skript aus dem Verzeichnis mit" >&2
    echo "        der docker-compose.yml / .env.example heraus aufrufen." >&2
    exit 1
fi

if [ -f .env ]; then
    echo "FEHLER: .env existiert bereits. Bitte manuell pruefen/ergaenzen — dieses" >&2
    echo "        Skript ueberschreibt keine bestehende .env." >&2
    exit 1
fi

# Zufallswert: openssl bevorzugt, sonst Python-Fallback.
gen() {
    local n="${1:-24}"
    openssl rand -hex "$n" 2>/dev/null \
        || python3 -c "import secrets,sys;print(secrets.token_hex(int(sys.argv[1])))" "$n"
}

cp .env.example .env

SECRET_KEY="$(gen 64)"
POSTGRES_PASSWORD="$(gen 24)"
APP_DB_PASSWORD="$(gen 24)"
GRAFANA_ADMIN_PASSWORD="$(gen 16)"
# Admin-Passwort komplex genug fuer die Production-Passwortpruefung
# (Gross-/Kleinbuchstaben, Ziffer, Sonderzeichen):
ADMIN_PASSWORD="$(gen 16)-Pz9!Aa"

# sed mit | als Delimiter — alle Werte sind hex/ASCII ohne | und ohne &.
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|"                     .env
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${POSTGRES_PASSWORD}|" .env
sed -i "s|^APP_DB_PASSWORD=.*|APP_DB_PASSWORD=${APP_DB_PASSWORD}|"       .env
sed -i "s|^GRAFANA_ADMIN_PASSWORD=.*|GRAFANA_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}|" .env
sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${ADMIN_PASSWORD}|"         .env
sed -i "s|^ENVIRONMENT=.*|ENVIRONMENT=production|"                      .env
# DATABASE_URL referenziert den App-User (Compose setzt sie ohnehin neu — hier
# nur zur Kohaerenz der .env):
sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql://praxiszeit_app:${APP_DB_PASSWORD}@db:5432/praxiszeit|" .env

chmod 600 .env

echo ""
echo "============================================================"
echo "  .env erzeugt — Secrets zufaellig gesetzt."
echo "------------------------------------------------------------"
echo "  Initiales Admin-Passwort: ${ADMIN_PASSWORD}"
echo "  (Nach dem ersten Login in der Benutzerverwaltung aendern!)"
echo "============================================================"
echo ""
echo "  Noch anpassen in .env, falls extern erreichbar:"
echo "    - CORS_ORIGINS   (eigene Domain statt localhost)"
echo "    - ADMIN_EMAIL / PRACTICE_NAME"
echo ""
echo "  HTTPS (empfohlen): zuerst ein Zertifikat erzeugen"
echo "    bash ssl/generate-cert.sh"
echo "  dann mit SSL-Overlay starten:"
echo "    docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build"
echo ""
