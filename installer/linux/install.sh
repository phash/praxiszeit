#!/bin/bash
# PraxisZeit Native Installer for Linux
# Installs PraxisZeit as a systemd service with embedded Python + PostgreSQL
set -euo pipefail

VERSION="@@VERSION@@"
INSTALL_DIR="/opt/praxiszeit"
SERVICE_USER="praxiszeit"
SERVICE_NAME="praxiszeit"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# --- Pre-flight checks ---

if [ "$EUID" -ne 0 ]; then
    error "This installer must be run as root (use sudo)."
    exit 1
fi

if ! command -v systemctl &>/dev/null; then
    error "systemd not found. This installer requires a systemd-based Linux distribution."
    exit 1
fi

echo ""
echo "=============================================="
echo "  PraxisZeit Installer v${VERSION}"
echo "  Zeiterfassung fuer Arztpraxen"
echo "=============================================="
echo ""

# --- Interactive configuration ---

read -rp "Praxis-Name: " PRACTICE_NAME
if [ -z "$PRACTICE_NAME" ]; then
    error "Praxis-Name darf nicht leer sein."
    exit 1
fi

echo ""
echo "Bundesland fuer Feiertage:"
echo "  1) Baden-Wuerttemberg    2) Bayern"
echo "  3) Berlin                4) Brandenburg"
echo "  5) Bremen                6) Hamburg"
echo "  7) Hessen                8) Mecklenburg-Vorpommern"
echo "  9) Niedersachsen        10) Nordrhein-Westfalen"
echo " 11) Rheinland-Pfalz      12) Saarland"
echo " 13) Sachsen              14) Sachsen-Anhalt"
echo " 15) Schleswig-Holstein   16) Thueringen"

STATES=(
    "Baden-Wuerttemberg" "Bayern" "Berlin" "Brandenburg"
    "Bremen" "Hamburg" "Hessen" "Mecklenburg-Vorpommern"
    "Niedersachsen" "Nordrhein-Westfalen" "Rheinland-Pfalz" "Saarland"
    "Sachsen" "Sachsen-Anhalt" "Schleswig-Holstein" "Thueringen"
)

read -rp "Bundesland [2]: " STATE_NUM
STATE_NUM=${STATE_NUM:-2}
if [ "$STATE_NUM" -lt 1 ] || [ "$STATE_NUM" -gt 16 ]; then
    error "Ungueltige Auswahl."
    exit 1
fi
HOLIDAY_STATE="${STATES[$((STATE_NUM - 1))]}"

echo ""
read -rp "Admin-Benutzername [admin]: " ADMIN_USERNAME
ADMIN_USERNAME=${ADMIN_USERNAME:-admin}

read -rp "Admin-E-Mail: " ADMIN_EMAIL
if [ -z "$ADMIN_EMAIL" ]; then
    error "Admin-E-Mail darf nicht leer sein."
    exit 1
fi

while true; do
    read -srp "Admin-Passwort (min. 12 Zeichen): " ADMIN_PASSWORD
    echo ""
    if [ ${#ADMIN_PASSWORD} -lt 12 ]; then
        warn "Passwort muss mindestens 12 Zeichen lang sein."
        continue
    fi
    read -srp "Passwort wiederholen: " ADMIN_PASSWORD2
    echo ""
    if [ "$ADMIN_PASSWORD" != "$ADMIN_PASSWORD2" ]; then
        warn "Passwoerter stimmen nicht ueberein."
        continue
    fi
    break
done

echo ""
read -rp "Lizenzschluessel-Datei (Pfad, oder leer fuer spaeter): " LICENSE_FILE

echo ""
read -rp "HTTPS-Port [443]: " PORT
PORT=${PORT:-443}

read -rp "Selbstsigniertes SSL-Zertifikat generieren? [J/n]: " GEN_SSL
GEN_SSL=${GEN_SSL:-J}

echo ""
read -rp "Installationsverzeichnis [${INSTALL_DIR}]: " CUSTOM_DIR
INSTALL_DIR=${CUSTOM_DIR:-$INSTALL_DIR}

# --- Confirmation ---

echo ""
echo "=============================================="
echo "  Installationszusammenfassung"
echo "=============================================="
echo "  Praxis:      ${PRACTICE_NAME}"
echo "  Bundesland:  ${HOLIDAY_STATE}"
echo "  Admin:       ${ADMIN_USERNAME} <${ADMIN_EMAIL}>"
echo "  Port:        ${PORT}"
echo "  SSL:         $([ "${GEN_SSL,,}" = "j" ] && echo 'Ja (selbstsigniert)' || echo 'Nein')"
echo "  Verzeichnis: ${INSTALL_DIR}"
echo "=============================================="
echo ""
read -rp "Installation starten? [J/n]: " CONFIRM
CONFIRM=${CONFIRM:-J}
if [ "${CONFIRM,,}" != "j" ]; then
    echo "Installation abgebrochen."
    exit 0
fi

# --- Installation ---

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

info "Erstelle System-Benutzer '${SERVICE_USER}'..."
if ! id "${SERVICE_USER}" &>/dev/null; then
    useradd --system --home-dir "${INSTALL_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

info "Erstelle Verzeichnisse..."
mkdir -p "${INSTALL_DIR}"/{bin,app,data/db,data/backups,config/ssl,logs}

info "Kopiere Anwendungsdateien..."
# The installer package should contain these directories at the same level
if [ -d "${SCRIPT_DIR}/bin" ]; then
    cp -r "${SCRIPT_DIR}/bin/"* "${INSTALL_DIR}/bin/"
fi
if [ -d "${SCRIPT_DIR}/app" ]; then
    cp -r "${SCRIPT_DIR}/app/"* "${INSTALL_DIR}/app/"
fi
if [ -f "${SCRIPT_DIR}/praxiszeit-server.py" ]; then
    cp "${SCRIPT_DIR}/praxiszeit-server.py" "${INSTALL_DIR}/"
fi

# --- Generate SECRET_KEY ---

SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(64))" 2>/dev/null || openssl rand -hex 64)

# --- Write configuration ---

info "Schreibe Konfiguration..."
cat > "${INSTALL_DIR}/config/praxiszeit.conf" << TOMLEOF
[server]
port = ${PORT}
$([ "${GEN_SSL,,}" = "j" ] && echo 'ssl_cert = "config/ssl/cert.pem"' || echo '# ssl_cert = ""')
$([ "${GEN_SSL,,}" = "j" ] && echo 'ssl_key = "config/ssl/key.pem"' || echo '# ssl_key = ""')

[database]
data_dir = "data/db"
superuser = "praxiszeit"
app_user = "praxiszeit_app"

[practice]
name = "${PRACTICE_NAME}"
holiday_state = "${HOLIDAY_STATE}"

[admin]
username = "${ADMIN_USERNAME}"
email = "${ADMIN_EMAIL}"
password = "${ADMIN_PASSWORD}"

[security]
secret_key = "${SECRET_KEY}"
login_rate_limit = "5/minute"
cookie_secure = $([ "${GEN_SSL,,}" = "j" ] && echo 'true' || echo 'false')

[license]
$([ -n "${LICENSE_FILE}" ] && echo "key_file = \"config/license.key\"" || echo '# key_file = "config/license.key"')

[updates]
check_enabled = true
server_url = "https://updates.praxiszeit.de"
check_interval_hours = 12

[backup]
enabled = true
schedule = "02:00"
retention_days = 31
TOMLEOF

# --- Copy license file ---

if [ -n "${LICENSE_FILE}" ] && [ -f "${LICENSE_FILE}" ]; then
    cp "${LICENSE_FILE}" "${INSTALL_DIR}/config/license.key"
    info "Lizenzschluessel kopiert"
fi

# --- Generate SSL certificate ---

if [ "${GEN_SSL,,}" = "j" ]; then
    info "Generiere selbstsigniertes SSL-Zertifikat..."
    SERVER_IP=$(hostname -I | awk '{print $1}')
    openssl req -x509 -newkey ed25519 -keyout "${INSTALL_DIR}/config/ssl/key.pem" \
        -out "${INSTALL_DIR}/config/ssl/cert.pem" -days 3650 -nodes \
        -subj "/CN=PraxisZeit/O=${PRACTICE_NAME}" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:${SERVER_IP}" \
        2>/dev/null
    info "SSL-Zertifikat generiert (10 Jahre gueltig)"
fi

# --- Set permissions ---

info "Setze Berechtigungen..."
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
chmod 600 "${INSTALL_DIR}/config/praxiszeit.conf"
chmod 600 "${INSTALL_DIR}/config/ssl/"*.pem 2>/dev/null || true

# --- Install systemd service ---

info "Installiere systemd Service..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << SVCEOF
[Unit]
Description=PraxisZeit Zeiterfassung
Documentation=https://github.com/phash/praxiszeit
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/bin/python/bin/python3 ${INSTALL_DIR}/praxiszeit-server.py start
ExecStop=${INSTALL_DIR}/bin/python/bin/python3 ${INSTALL_DIR}/praxiszeit-server.py stop
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${INSTALL_DIR}/data ${INSTALL_DIR}/logs ${INSTALL_DIR}/config
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"

# --- Setup backup cron ---

info "Richte taegliches Backup ein (02:00)..."
CRON_CMD="${INSTALL_DIR}/bin/python/bin/python3 ${INSTALL_DIR}/praxiszeit-server.py backup"
(crontab -u "${SERVICE_USER}" -l 2>/dev/null || true; echo "0 2 * * * ${CRON_CMD}") | crontab -u "${SERVICE_USER}" -

# --- Start service ---

info "Starte PraxisZeit..."
systemctl start "${SERVICE_NAME}"

# Wait for startup
for i in $(seq 1 30); do
    if curl -sk "https://localhost:${PORT}/api/health" 2>/dev/null | grep -q "healthy"; then
        break
    fi
    sleep 1
done

echo ""
echo "=============================================="
echo -e "  ${GREEN}PraxisZeit erfolgreich installiert!${NC}"
echo "=============================================="
echo ""
echo "  URL:       https://$(hostname -I | awk '{print $1}'):${PORT}"
echo "  Admin:     ${ADMIN_USERNAME}"
echo "  Service:   systemctl {start|stop|status} ${SERVICE_NAME}"
echo "  Logs:      ${INSTALL_DIR}/logs/"
echo "  Backups:   ${INSTALL_DIR}/data/backups/"
echo ""
echo "  WICHTIG: Aendern Sie das Admin-Passwort nach dem"
echo "  ersten Login ueber die Benutzerverwaltung!"
echo ""
