#!/bin/bash
# PraxisZeit Local Installer (System-Pakete)
# Nutzt systemweit installiertes Python + PostgreSQL statt gebündelter Binaries.
# Für lokale Tests und Entwicklung.
set -euo pipefail

VERSION="1.2.0"
INSTALL_DIR="${1:-/opt/praxiszeit}"
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}>>>${NC} $*"; }
warn()  { echo -e "${YELLOW}>>>${NC} $*"; }
error() { echo -e "${RED}>>>${NC} $*" >&2; }

echo ""
echo "=============================================="
echo "  PraxisZeit Local Installer v${VERSION}"
echo "  (System-Pakete, kein Docker)"
echo "=============================================="
echo ""

# --- Pre-flight ---

if [ "$EUID" -ne 0 ]; then
    error "Bitte mit sudo ausfuehren: sudo $0 [install-dir]"
    exit 1
fi

for cmd in python3 pg_isready initdb pg_ctl psql; do
    if ! command -v "$cmd" &>/dev/null; then
        error "'$cmd' nicht gefunden. Bitte installieren:"
        error "  Arch: sudo pacman -S postgresql python"
        error "  Ubuntu: sudo apt install postgresql python3 python3-venv"
        exit 1
    fi
done

info "Python: $(python3 --version)"
info "PostgreSQL: $(pg_isready --version 2>/dev/null || psql --version)"
info "Repo: ${REPO_DIR}"
info "Ziel: ${INSTALL_DIR}"
echo ""

# --- Konfiguration abfragen ---

read -rp "Praxis-Name [Testpraxis]: " PRACTICE_NAME
PRACTICE_NAME=${PRACTICE_NAME:-Testpraxis}

read -rp "Admin-E-Mail [admin@local.test]: " ADMIN_EMAIL
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@local.test}

read -rp "Admin-Passwort [Admin2025!test]: " ADMIN_PASSWORD
ADMIN_PASSWORD=${ADMIN_PASSWORD:-Admin2025!test}

read -rp "HTTP-Port [8443]: " PORT
PORT=${PORT:-8443}

echo ""
read -rp "Installation starten? [J/n]: " CONFIRM
CONFIRM=${CONFIRM:-J}
if [ "${CONFIRM,,}" != "j" ]; then
    echo "Abgebrochen."
    exit 0
fi

# --- Verzeichnisstruktur ---

info "Erstelle Verzeichnisse..."
mkdir -p "${INSTALL_DIR}"/{data/db,data/backups,config/ssl,logs}

# --- Python venv statt gebündeltem Python ---

info "Erstelle Python Virtual Environment..."
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install -q --upgrade pip

info "Installiere Python-Abhaengigkeiten..."
"${INSTALL_DIR}/venv/bin/pip" install -q -r "${REPO_DIR}/backend/requirements.txt"

# --- Anwendungsdateien kopieren ---

info "Kopiere Backend..."
mkdir -p "${INSTALL_DIR}/app/backend"
cp -r "${REPO_DIR}/backend/app" "${INSTALL_DIR}/app/backend/"
cp -r "${REPO_DIR}/backend/alembic" "${INSTALL_DIR}/app/backend/"
cp "${REPO_DIR}/backend/alembic.ini" "${INSTALL_DIR}/app/backend/"
cp "${REPO_DIR}/backend/init-db-user.sql" "${INSTALL_DIR}/app/backend/"

info "Baue Frontend..."
if [ -d "${REPO_DIR}/frontend/dist" ]; then
    info "Frontend-Build gefunden, kopiere..."
    mkdir -p "${INSTALL_DIR}/app/frontend"
    cp -r "${REPO_DIR}/frontend/dist/"* "${INSTALL_DIR}/app/frontend/"
else
    warn "Kein Frontend-Build gefunden (frontend/dist/)."
    warn "Bitte 'cd frontend && npm run build' ausfuehren und erneut installieren."
fi

# --- Process Manager (angepasst fuer System-Pakete) ---

info "Installiere Process Manager..."
cp "${REPO_DIR}/praxiszeit-server.py" "${INSTALL_DIR}/"

# Wrapper-Script das System-PostgreSQL-Binaries und venv nutzt
cat > "${INSTALL_DIR}/start.sh" << 'STARTEOF'
#!/bin/bash
# PraxisZeit Start-Wrapper
DIR="$(cd "$(dirname "$0")" && pwd)"

# PostgreSQL-Binaries aus System-PATH nutzen
export PATH="/usr/bin:$PATH"

# Python aus venv
exec "${DIR}/venv/bin/python3" "${DIR}/praxiszeit-server.py" "$@"
STARTEOF
chmod +x "${INSTALL_DIR}/start.sh"

# Patch: Process Manager soll System-PG-Binaries finden
# Symlink bin/postgresql/bin -> /usr/bin (wo pg_ctl etc. liegen)
mkdir -p "${INSTALL_DIR}/bin/postgresql"
ln -sfn "/usr/bin" "${INSTALL_DIR}/bin/postgresql/bin"

# --- Secret Key generieren ---

SECRET_KEY=$("${INSTALL_DIR}/venv/bin/python3" -c "import secrets; print(secrets.token_hex(64))")

# --- Konfiguration schreiben ---

info "Schreibe Konfiguration..."
cat > "${INSTALL_DIR}/config/praxiszeit.conf" << CONFEOF
[server]
port = ${PORT}
# Kein SSL fuer lokalen Test
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

chmod 600 "${INSTALL_DIR}/config/praxiszeit.conf"

# --- Benutzer ---

info "Erstelle System-Benutzer 'praxiszeit'..."
if ! id praxiszeit &>/dev/null; then
    useradd --system --home-dir "${INSTALL_DIR}" --shell /usr/sbin/nologin praxiszeit
fi
chown -R praxiszeit:praxiszeit "${INSTALL_DIR}"

# --- systemd Service ---

info "Installiere systemd Service..."
cat > /etc/systemd/system/praxiszeit.service << SVCEOF
[Unit]
Description=PraxisZeit Zeiterfassung
After=network.target
# #427: Ohne Obergrenze startet systemd endlos neu und der Dienst wechselt
# staendig zwischen "activating" und "auto-restart" — er endet nie in "failed".
# Fuenf Fehlversuche in fuenf Minuten (bei RestartSec=10 also ein anhaltender
# Fehler, kein einmaliger Ausrutscher) fuehren jetzt zu einem ehrlichen
# "failed", das `systemctl status` auch anzeigt. Beide Schluessel gehoeren seit
# systemd 230 in [Unit]; in [Service] werden sie kommentarlos ignoriert.
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=praxiszeit
Group=praxiszeit
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/start.sh start
ExecStop=${INSTALL_DIR}/start.sh stop
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable praxiszeit

# --- Fertig ---

echo ""
echo "=============================================="
echo -e "  ${GREEN}PraxisZeit installiert!${NC}"
echo "=============================================="
echo ""
echo "  Verzeichnis:  ${INSTALL_DIR}"
echo "  Starten:      sudo systemctl start praxiszeit"
echo "  Status:       sudo systemctl status praxiszeit"
echo "  Logs:         ${INSTALL_DIR}/logs/praxiszeit.log"
echo "  Manuell:      sudo -u praxiszeit ${INSTALL_DIR}/start.sh start"
echo ""
echo "  Nach dem Start erreichbar unter:"
echo "    http://localhost:${PORT}"
echo ""
echo "  Login: admin / ${ADMIN_PASSWORD}"
echo ""
