#!/bin/bash
# PraxisZeit Installer fuer macOS (Intel + Apple Silicon)
# PostgreSQL wird via EDB-Installer (DMG) silent installiert.
set -euo pipefail

VERSION="@@VERSION@@"
INSTALL_DIR="${1:-/usr/local/praxiszeit}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}>>>${NC} $*"; }
warn()  { echo -e "${YELLOW}>>>${NC} $*"; }
error() { echo -e "${RED}>>>${NC} $*" >&2; }

echo ""
echo "=============================================="
echo "  PraxisZeit Installer v${VERSION} (macOS)"
echo "=============================================="
echo ""

if [ "$EUID" -ne 0 ]; then
    error "Bitte mit sudo ausfuehren: sudo $0 [install-dir]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Konfiguration abfragen ---

# #421: Bei einem Update bleibt die bestehende praxiszeit.conf erhalten (siehe
# unten) — inklusive Admin-Konto, Passwort und Sicherheitsschluessel. Danach zu
# fragen ist irrefuehrend: der Betreiber tippt ein Passwort ein, das nirgends
# ankommt, und kann sich anschliessend nicht damit anmelden. Im Update-Fall
# also gar nicht erst fragen. Parität zum Linux-Installer.
UPDATE_MODE=0
if [ -f "${INSTALL_DIR}/config/praxiszeit.conf" ]; then
    UPDATE_MODE=1
fi

if [ "$UPDATE_MODE" = "1" ]; then
    info "Bestehende Installation in ${INSTALL_DIR} erkannt -> UPDATE."
    echo "  Konfiguration und Zugangsdaten bleiben unveraendert (Admin-Konto,"
    echo "  Passwort, Port, Sicherheitsschluessel). Ihr bisheriges Admin-Passwort"
    echo "  gilt weiter. Eingespielt werden nur Code und Datenbank-Migrationen."
    PORT=$(sed -n 's/^[[:space:]]*port[[:space:]]*=[[:space:]]*//p' "${INSTALL_DIR}/config/praxiszeit.conf" 2>/dev/null | head -1 | tr -d '"')
    PORT=${PORT:-8443}
else

read -rp "Praxis-Name [Testpraxis]: " PRACTICE_NAME
PRACTICE_NAME=${PRACTICE_NAME:-Testpraxis}

read -rp "Admin-E-Mail [admin@local.test]: " ADMIN_EMAIL
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@local.test}

while true; do
    read -rp "Admin-Passwort (min. 12 Zeichen): " ADMIN_PASSWORD
    [ ${#ADMIN_PASSWORD} -ge 12 ] && break
    warn "Passwort zu kurz."
done

read -rp "Port [8443]: " PORT
PORT=${PORT:-8443}

fi   # Ende des Erstinstallations-Zweigs (#421)

echo ""
info "Installiere nach ${INSTALL_DIR}..."

# --- PostgreSQL installieren ---

PG_INSTALL_DIR="${INSTALL_DIR}/bin/postgresql"
PG_DMG="${SCRIPT_DIR}/bin/postgresql-installer.dmg"

if [ -d "${PG_INSTALL_DIR}/bin" ] && [ -f "${PG_INSTALL_DIR}/bin/pg_ctl" ]; then
    info "PostgreSQL bereits installiert, ueberspringe..."
elif [ -f "$PG_DMG" ]; then
    info "Installiere PostgreSQL (silent, kann einige Minuten dauern)..."

    # DMG mounten
    MOUNT_POINT=$(hdiutil attach -nobrowse -mountpoint /tmp/pg-dmg "$PG_DMG" 2>/dev/null | tail -1 | awk '{print $NF}')
    if [ -z "$MOUNT_POINT" ]; then
        MOUNT_POINT="/tmp/pg-dmg"
    fi

    # Installer im DMG finden
    # awk 'NR==1' statt '| head -1': head -1 schliesst die Pipe nach Zeile 1 ->
    # find bekommt SIGPIPE, und mit `set -o pipefail` (Zeile 4) liefert das $(...)
    # dann 141 -> set -e killt den Installer. awk liest den Stream komplett.
    PG_APP=$(find "$MOUNT_POINT" -name "postgresql-*.app" -maxdepth 1 2>/dev/null | awk 'NR==1')
    if [ -z "$PG_APP" ]; then
        # Fallback: .app im Root oder MacOS-Binary
        PG_APP=$(find "$MOUNT_POINT" -name "*.app" -maxdepth 1 2>/dev/null | awk 'NR==1')
    fi

    if [ -n "$PG_APP" ]; then
        # EDB Installer (BitRock) — gleiche Flags wie Windows
        PG_INSTALLER="${PG_APP}/Contents/MacOS/installbuilder.sh"
        if [ ! -f "$PG_INSTALLER" ]; then
            PG_INSTALLER="${PG_APP}/Contents/MacOS/osx-intel"
            [ ! -f "$PG_INSTALLER" ] && PG_INSTALLER="${PG_APP}/Contents/MacOS/osx-arm64"
        fi

        if [ -f "$PG_INSTALLER" ]; then
            # F-025: Generate a random one-shot password for the EDB installer.
            # The EDB PostgreSQL service+data is replaced later by praxiszeit-server.py
            # which runs initdb with its own secrets.token_hex(32) credentials
            # persisted in .db-credentials. The one-shot password only has to
            # live long enough for the installer itself to run.
            # openssl rand statt `tr </dev/urandom | head -c 32`: head -c schliesst
            # die Pipe -> tr (liest /dev/urandom endlos) bekommt SIGPIPE -> pipefail
            # + set -e killen den Installer (nahezu sicher). openssl rand hat keine
            # Pipe und liefert 32 alphanumerische (hex) Zeichen.
            EDB_SU_PW="$(openssl rand -hex 16)"
            "$PG_INSTALLER" \
                --mode unattended \
                --unattendedmodeui none \
                --prefix "${PG_INSTALL_DIR}" \
                --datadir "${INSTALL_DIR}/data/db" \
                --superpassword "${EDB_SU_PW}" \
                --serverport 5432 \
                --disable-components stackbuilder,pgAdmin \
                --install_runtimes 0 \
                2>/dev/null || true
            # Drop the one-shot password from memory immediately
            unset EDB_SU_PW
            info "PostgreSQL installiert"
        else
            warn "Kann PostgreSQL-Installer im DMG nicht finden"
            warn "Bitte PostgreSQL manuell installieren: https://postgresapp.com"
        fi
    else
        warn "Keine .app im DMG gefunden"
        warn "Bitte PostgreSQL manuell installieren: https://postgresapp.com"
    fi

    # DMG unmounten
    hdiutil detach "$MOUNT_POINT" 2>/dev/null || true
else
    warn "Kein PostgreSQL-Installer gefunden."
    warn "Bitte installieren Sie PostgreSQL:"
    warn "  Option A: https://postgresapp.com (empfohlen)"
    warn "  Option B: brew install postgresql@16"
    warn ""
    warn "Danach Symlink erstellen:"
    warn "  ln -s /Applications/Postgres.app/Contents/Versions/latest ${PG_INSTALL_DIR}"
fi

# --- Python pip-Dependencies ---

PYTHON="${SCRIPT_DIR}/bin/python/bin/python3"
if [ ! -f "$PYTHON" ]; then
    error "Python nicht gefunden: $PYTHON"
    exit 1
fi

info "Installiere Python-Dependencies..."
if [ -f "${SCRIPT_DIR}/bin/python/get-pip.py" ]; then
    "$PYTHON" "${SCRIPT_DIR}/bin/python/get-pip.py" --quiet 2>/dev/null || true
fi
"$PYTHON" -m pip install --quiet -r "${SCRIPT_DIR}/app/backend/requirements.txt"

# --- Dateien kopieren ---

info "Kopiere Anwendungsdateien..."
mkdir -p "${INSTALL_DIR}"/{data/db,data/backups,config/ssl,logs}
cp -R "${SCRIPT_DIR}/bin" "${INSTALL_DIR}/"
cp -R "${SCRIPT_DIR}/app" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/praxiszeit-server.py" "${INSTALL_DIR}/"

# --- Konfiguration schreiben ---

SECRET_KEY=$("${INSTALL_DIR}/bin/python/bin/python3" -c "import secrets; print(secrets.token_hex(64))")

if [ -f "${INSTALL_DIR}/config/praxiszeit.conf" ]; then
    # Reinstall/Update: bestehende Konfiguration NICHT ueberschreiben. Ein neu
    # generierter secret_key wuerde sonst alle Sessions ungueltig machen UND alle
    # verschluesselten TOTP-Secrets (Migration 050) unentschluesselbar -> jeder
    # 2FA-Nutzer ausgesperrt. port/retention/Admin-Passwort bleiben so erhalten.
    info "Bestehende config/praxiszeit.conf erkannt -> wird beibehalten (Reinstall/Update)."
else
info "Schreibe Konfiguration..."
cat > "${INSTALL_DIR}/config/praxiszeit.conf" << CONFEOF
[server]
port = ${PORT}
ssl_cert = ""
ssl_key = ""

[database]
data_dir = "data/db"
superuser = "praxiszeit"
app_user = "praxiszeit_app"

[practice]
name = "${PRACTICE_NAME}"
holiday_state = "Bayern"

[admin]
username = "admin"
email = "${ADMIN_EMAIL}"
password = "${ADMIN_PASSWORD}"

[security]
secret_key = "${SECRET_KEY}"
login_rate_limit = "10/minute"
cookie_secure = false

[license]
# key_file = "config/license.key"

[updates]
check_enabled = false

[backup]
enabled = true
schedule = "02:00"
retention_days = 31
CONFEOF
fi
chmod 600 "${INSTALL_DIR}/config/praxiszeit.conf"

# --- Service-User ---

if ! dscl . -read /Users/_praxiszeit &>/dev/null 2>&1; then
    info "Erstelle Service-User _praxiszeit..."
    LAST_UID=$(dscl . -list /Users UniqueID | awk '{print $2}' | sort -n | tail -1)
    NEXT_UID=$((LAST_UID + 1))
    dscl . -create /Users/_praxiszeit
    dscl . -create /Users/_praxiszeit UniqueID "$NEXT_UID"
    dscl . -create /Users/_praxiszeit PrimaryGroupID 20
    dscl . -create /Users/_praxiszeit UserShell /usr/bin/false
    dscl . -create /Users/_praxiszeit NFSHomeDirectory "${INSTALL_DIR}"
fi
chown -R _praxiszeit:staff "${INSTALL_DIR}"

# --- launchd Service ---

info "Installiere launchd Service..."
cat > /Library/LaunchDaemons/de.praxiszeit.server.plist << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>de.praxiszeit.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>${INSTALL_DIR}/bin/python/bin/python3</string>
        <string>${INSTALL_DIR}/praxiszeit-server.py</string>
        <string>start</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${INSTALL_DIR}</string>
    <key>UserName</key>
    <string>_praxiszeit</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${INSTALL_DIR}/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${INSTALL_DIR}/logs/stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>
PLISTEOF

launchctl load /Library/LaunchDaemons/de.praxiszeit.server.plist

info "Richte taegliches Backup ein (launchd, 03:00)..."
cat > /Library/LaunchDaemons/de.praxiszeit.backup.plist << BKPLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>de.praxiszeit.backup</string>
    <key>ProgramArguments</key>
    <array>
        <string>${INSTALL_DIR}/bin/python/bin/python3</string>
        <string>${INSTALL_DIR}/praxiszeit-server.py</string>
        <string>backup</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${INSTALL_DIR}</string>
    <key>UserName</key>
    <string>_praxiszeit</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>3</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${INSTALL_DIR}/logs/backup.log</string>
    <key>StandardErrorPath</key>
    <string>${INSTALL_DIR}/logs/backup.log</string>
</dict>
</plist>
BKPLISTEOF

launchctl load /Library/LaunchDaemons/de.praxiszeit.backup.plist

# --- Fertig ---

echo ""
echo "=============================================="
echo -e "  ${GREEN}PraxisZeit installiert!${NC}"
echo "=============================================="
echo ""
echo "  URL:      http://localhost:${PORT}"
echo "  Login:    admin / (Ihr Passwort)"
echo ""
echo "  Starten:  sudo launchctl load /Library/LaunchDaemons/de.praxiszeit.server.plist"
echo "  Stoppen:  sudo launchctl unload /Library/LaunchDaemons/de.praxiszeit.server.plist"
echo "  Logs:     ${INSTALL_DIR}/logs/"
echo ""
