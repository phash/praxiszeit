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

# --- glibc version check ---
# Bundled PostgreSQL binary verlangt glibc >= 2.34 (manylinux-Build).
# awk 'NR==1' statt '| head -1 | awk': head -1 schliesst die Pipe nach der ersten
# Zeile -> ldd bekommt SIGPIPE (141), und mit `set -o pipefail` (Zeile 4) liefert
# die $(...)-Substitution dann 141 -> `set -e` killt den Installer VOR jeder
# Ausgabe (racy, je nach ldd-Timing). awk liest den Stream komplett -> kein SIGPIPE.
GLIBC_VER=$(ldd --version 2>&1 | awk 'NR==1{print $NF}')
GLIBC_MAJOR=${GLIBC_VER%%.*}
GLIBC_MINOR=${GLIBC_VER#*.}
GLIBC_MINOR=${GLIBC_MINOR%%.*}
if [ "$GLIBC_MAJOR" -lt 2 ] || { [ "$GLIBC_MAJOR" -eq 2 ] && [ "$GLIBC_MINOR" -lt 34 ]; }; then
    error "glibc ${GLIBC_VER} ist zu alt. Erforderlich: glibc 2.34 oder neuer."
    error "Unterstuetzte Distributionen:"
    error "  - Ubuntu 22.04 LTS und neuer"
    error "  - Debian 12 (Bookworm) und neuer"
    error "  - RHEL / Rocky / Alma Linux 9 und neuer"
    error "  - Fedora 35 und neuer"
    exit 1
fi

# --- Install required runtime libraries ---
# Theseus' postgres binary linkt gegen Standard-Distro-Libs (libxml2, libssl,
# libgssapi-krb5, libldap, libreadline, libzstd, liblz4, libbrotli). Wir
# installieren die fehlenden Pakete jetzt, damit der PG-Start nicht an
# "shared library not found" scheitert.
install_runtime_deps() {
    # ldconfig-Ausgabe EINMAL in eine Variable lesen und per Here-String matchen.
    # NICHT `ldconfig -p | grep -q` verwenden: grep -q beendet bei Treffer frueh,
    # ldconfig bekommt SIGPIPE (Exit 141), und mit `set -o pipefail` (Zeile 4)
    # wird die Pipeline dadurch non-zero -> `if !` schlaegt um -> auf Hosts mit
    # VIELEN Libs (lange ldconfig-Ausgabe, z.B. Desktop) wird die Lib faelschlich
    # als "missing" gemeldet bzw. unten die Rolling-Distro-Bremse falsch ausgeloest
    # (Feldreport Mint/Ubuntu 24.04, 2026-06; minimale Validate-Container mit kurzer
    # ldconfig-Ausgabe maskierten den Bug). Here-String = keine Pipe -> kein SIGPIPE.
    local ldcache
    ldcache=$(ldconfig -p 2>/dev/null || true)
    local missing=()
    for lib in libxml2.so.2 libssl.so.3 libgssapi_krb5.so.2 libzstd.so.1 liblz4.so.1 libreadline.so.8 libbrotlidec.so.1; do
        if ! grep -q "^[[:space:]]*${lib}\b" <<<"$ldcache"; then
            missing+=("$lib")
        fi
    done
    if [ "${#missing[@]}" -eq 0 ]; then
        info "Alle erforderlichen Runtime-Bibliotheken sind vorhanden."
        return 0
    fi

    info "Installiere fehlende Runtime-Bibliotheken: ${missing[*]}"
    if command -v apt-get &>/dev/null; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq \
            libxml2 libssl3 libgssapi-krb5-2 libzstd1 liblz4-1 libreadline8 libbrotli1 \
            || { error "apt-get install fehlgeschlagen"; exit 1; }
    elif command -v dnf &>/dev/null; then
        dnf install -y -q \
            libxml2 openssl-libs krb5-libs libzstd lz4-libs readline libbrotli \
            || { error "dnf install fehlgeschlagen"; exit 1; }
    elif command -v zypper &>/dev/null; then
        zypper -n install \
            libxml2-2 libopenssl3 krb5 libzstd1 liblz4-1 libreadline8 libbrotli1 \
            || { error "zypper install fehlgeschlagen"; exit 1; }
    elif command -v pacman &>/dev/null; then
        # Arch/CachyOS. KEIN -Sy (Partial-Upgrade-Falle) — --needed nutzt die
        # vorhandene Sync-DB. ACHTUNG: Rolling-Distros koennen libxml2 bereits
        # auf einen neueren Soname (libxml2.so.16) gehoben haben; theseus' PG
        # braucht libxml2.so.2 — dann unten der Hinweis.
        pacman -S --needed --noconfirm \
            libxml2 openssl krb5 zstd lz4 readline brotli \
            || { error "pacman install fehlgeschlagen (ggf. zuerst 'pacman -Sy')"; exit 1; }
    else
        error "Kein bekannter Paketmanager (apt-get, dnf, zypper, pacman) gefunden."
        error "Bitte installiere manuell: ${missing[*]}"
        exit 1
    fi

    # Rolling-Distro-Soname-Check: theseus' postgres linkt gegen libxml2.so.2.
    # Arch/CachyOS liefern ab libxml2 2.14 nur noch libxml2.so.16 -> der
    # PG-Start wuerde mit "libxml2.so.2: cannot open shared object file"
    # scheitern. Frueh + klar abbrechen statt im Dienst-Crash-Loop zu landen.
    ldcache=$(ldconfig -p 2>/dev/null || true)   # nach apt/dnf/zypper/pacman neu einlesen
    if ! grep -qE "^[[:space:]]*libxml2\.so\.2\b" <<<"$ldcache"; then
        error "libxml2.so.2 ist auf diesem System nicht verfuegbar."
        error "Vermutlich eine Rolling-Distro (z.B. Arch/CachyOS) mit libxml2 >= 2.14"
        error "(nur libxml2.so.16). Die mitgelieferte PostgreSQL benoetigt aber"
        error "libxml2.so.2. Unterstuetzt: Debian 12+, Ubuntu 22.04+, RHEL/Rocky/Alma 9+."
        exit 1
    fi
}

install_runtime_deps

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

# Beta (1.8.0): KEINE Lizenz-Abfrage — die Lizenzprüfung ist über BETA_MODE
# deaktiviert (keine Lizenz nötig). Eine vorhandene license.key (neben dem
# Installer oder aus einer früheren Installation) wird STILL übernommen, damit
# sie für eine spätere Reaktivierung erhalten bleibt; es wird aber nicht danach
# gefragt und nichts dazu angezeigt.
_PKG_DIR="$(cd "$(dirname "$0")" && pwd)"
LICENSE_FILE=""
if [ -f "${_PKG_DIR}/license.key" ]; then
    LICENSE_FILE="${_PKG_DIR}/license.key"
fi

echo ""
read -rp "HTTPS-Port [443]: " PORT
PORT=${PORT:-443}
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    error "Ungueltiger Port '${PORT}'. Erlaubt: 1-65535."
    exit 1
fi

read -rp "Selbstsigniertes SSL-Zertifikat generieren? [J/n]: " GEN_SSL
GEN_SSL=${GEN_SSL:-J}

echo ""
read -rp "Installationsverzeichnis [${INSTALL_DIR}]: " CUSTOM_DIR
INSTALL_DIR=${CUSTOM_DIR:-$INSTALL_DIR}

# Bestehende Lizenz aus einer früheren Installation übernehmen, wenn keine neue
# Datei angegeben wurde (Reinstall/Upgrade in dasselbe Verzeichnis) — dann wird
# config/license.key nicht überschrieben und bleibt aktiv.
EXISTING_LICENSE=0
if [ -z "${LICENSE_FILE}" ] && [ -f "${INSTALL_DIR}/config/license.key" ]; then
    EXISTING_LICENSE=1
    info "Vorhandene Lizenz in ${INSTALL_DIR}/config/license.key gefunden — wird beibehalten."
fi

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

# Issue #217: Bei einer Re-Installation/Update ueber eine noch LAUFENDE Instanz
# sind die gebuendelten Binaries (postgres, python3.13) gemappt -> "Text file
# busy", und das folgende cp scheitert semi-stumm. Darum den Dienst – falls
# vorhanden und aktiv – vorher stoppen (wird am Ende wieder gestartet). Stoppt
# zugleich die als Kind laufende PostgreSQL, sodass die Binaries frei sind.
if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
    info "Bestehender Dienst '${SERVICE_NAME}' laeuft — wird fuer das Update gestoppt..."
    systemctl stop "${SERVICE_NAME}"
    # Kurze Pause: das als Kind laufende postgres gibt die gemappten Binaries
    # erst nach dem Cgroup-Stop frei (sonst vereinzelt weiter "Text file busy").
    sleep 2
fi

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

# TOML-Werte escapen: Praxis-Name, Admin-Username, E-Mail UND Passwort sind
# freie Nutzereingaben. Ein " oder \ darin wuerde die praxiszeit.conf
# syntaktisch zerstoeren (load_config()->tomllib->TOMLDecodeError -> Dienst
# startet nicht) oder zusaetzliche TOML-Keys injizieren. tomllib entschluesselt
# \" / \\ beim Lesen wieder zurueck -> Passwort/Name round-trippen korrekt.
# Backslash zuerst ersetzen, dann das doppelte Anfuehrungszeichen.
toml_escape() { local s="$1"; s="${s//\\/\\\\}"; s="${s//\"/\\\"}"; printf '%s' "$s"; }
PRACTICE_NAME_ESC=$(toml_escape "$PRACTICE_NAME")
ADMIN_USERNAME_ESC=$(toml_escape "$ADMIN_USERNAME")
ADMIN_EMAIL_ESC=$(toml_escape "$ADMIN_EMAIL")
ADMIN_PASSWORD_ESC=$(toml_escape "$ADMIN_PASSWORD")

if [ -f "${INSTALL_DIR}/config/praxiszeit.conf" ]; then
    # Reinstall/Update: bestehende Konfiguration NICHT ueberschreiben. Ein neu
    # generierter secret_key wuerde sonst alle Sessions ungueltig machen UND alle
    # verschluesselten TOTP-Secrets (Migration 050) unentschluesselbar -> jeder
    # 2FA-Nutzer ausgesperrt. Auch port/SSL/retention/Admin-Passwort des Betreibers
    # bleiben so erhalten. Neue Eingaben aus diesem Lauf werden bewusst ignoriert.
    info "Bestehende config/praxiszeit.conf erkannt -> wird beibehalten (Reinstall/Update)."
else
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
name = "${PRACTICE_NAME_ESC}"
holiday_state = "${HOLIDAY_STATE}"

[admin]
username = "${ADMIN_USERNAME_ESC}"
email = "${ADMIN_EMAIL_ESC}"
password = "${ADMIN_PASSWORD_ESC}"

[security]
secret_key = "${SECRET_KEY}"
login_rate_limit = "5/minute"
cookie_secure = $([ "${GEN_SSL,,}" = "j" ] && echo 'true' || echo 'false')

[license]
$( { [ -n "${LICENSE_FILE}" ] || [ "${EXISTING_LICENSE}" = "1" ]; } && echo "key_file = \"config/license.key\"" || echo '# key_file = "config/license.key"')

[updates]
check_enabled = true
server_url = "https://updates.mr-development.de"
check_interval_hours = 12

[backup]
enabled = true
schedule = "02:00"
retention_days = 31
TOMLEOF
fi

# Passwort nicht laenger als noetig im Shell-Environment des Installers halten
# (war via /proc/self/environ fuer Co-Prozesse lesbar). Es steht jetzt escaped
# in der 0600-conf; der Backend-Erststart liest es von dort.
unset ADMIN_PASSWORD ADMIN_PASSWORD2 ADMIN_PASSWORD_ESC

# --- Copy license file ---

if [ -n "${LICENSE_FILE}" ] && [ -f "${LICENSE_FILE}" ]; then
    # Nicht auf sich selbst kopieren (falls die Quelle bereits config/license.key ist)
    if [ "$(readlink -f "${LICENSE_FILE}")" != "$(readlink -f "${INSTALL_DIR}/config/license.key" 2>/dev/null)" ]; then
        cp "${LICENSE_FILE}" "${INSTALL_DIR}/config/license.key"
    fi
    info "Lizenzschlüssel übernommen"
elif [ "${EXISTING_LICENSE}" = "1" ]; then
    info "Bestehende Lizenz beibehalten (${INSTALL_DIR}/config/license.key)"
fi

# --- Generate SSL certificate ---

if [ "${GEN_SSL,,}" = "j" ]; then
    info "Generiere selbstsigniertes SSL-Zertifikat..."
    SERVER_IP=$(hostname -I | awk '{print $1}')
    # Nur gueltige IP-Zeichen behalten — hostname-Output ist system-, aber nicht
    # garantiert sauber (DNS-Fehlkonfig); ungefilterte Kommas/Metazeichen wuerden
    # die openssl -addext "subjectAltName=..."-Liste verfaelschen.
    SERVER_IP=$(printf '%s' "$SERVER_IP" | tr -cd '0-9a-fA-F.:')
    # SAN konditionell zusammenbauen: ein leeres SERVER_IP (IPv6-only / nur
    # loopback) liesse openssl mit "IP:" leer abbrechen — vorher schluckte
    # 2>/dev/null den Fehler und es wurde KEIN Cert geschrieben, obwohl "OK"
    # gemeldet wurde. Hostname mitnehmen (Zugriff via https://<host>/).
    SAN="DNS:localhost,IP:127.0.0.1"
    [ -n "${SERVER_IP}" ] && SAN="${SAN},IP:${SERVER_IP}"
    HOST_FQDN=$(hostname -f 2>/dev/null || hostname 2>/dev/null || true)
    # Nur Hostname-Zeichen behalten (Buchstaben/Ziffern/Punkt/Bindestrich) — ein
    # Komma im FQDN wuerde sonst einen zusaetzlichen DNS-SAN-Eintrag erzeugen.
    HOST_FQDN=$(printf '%s' "$HOST_FQDN" | tr -cd 'a-zA-Z0-9.-')
    [ -n "${HOST_FQDN}" ] && [ "${HOST_FQDN}" != "localhost" ] && SAN="${SAN},DNS:${HOST_FQDN}"
    # RSA-2048 statt ed25519: Browser (Firefox/NSS, Chrome) unterstuetzen
    # Ed25519-TLS-SERVER-Zertifikate praktisch nicht -> harter Handshake-Fehler
    # OHNE "Erweitert"/Ausnahme-Option (Feldreport 2026-06).
    # basicConstraints=CA:FALSE + keyUsage + extendedKeyUsage=serverAuth machen
    # daraus ein gueltiges End-Entity-Server-Zertifikat statt eines CA-Certs
    # (ein CA-Cert wird vom Browser nicht als Server-Cert akzeptiert).
    # Fehler NICHT verschlucken: schlaegt openssl fehl, soll der Install es zeigen.
    if openssl req -x509 -newkey rsa:2048 -keyout "${INSTALL_DIR}/config/ssl/key.pem" \
        -out "${INSTALL_DIR}/config/ssl/cert.pem" -days 3650 -nodes \
        -subj "/CN=PraxisZeit/O=${PRACTICE_NAME}" \
        -addext "subjectAltName=${SAN}" \
        -addext "basicConstraints=critical,CA:FALSE" \
        -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
        -addext "extendedKeyUsage=serverAuth"; then
        info "SSL-Zertifikat generiert (10 Jahre gueltig, SAN: ${SAN})"
    else
        warn "SSL-Zertifikat konnte nicht erzeugt werden — PraxisZeit erzeugt beim ersten Start automatisch eines."
    fi
fi

# --- Set permissions ---

info "Setze Berechtigungen..."
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
chmod 600 "${INSTALL_DIR}/config/praxiszeit.conf"
chmod 600 "${INSTALL_DIR}/config/ssl/"*.pem 2>/dev/null || true

# --- Install systemd service ---

# Der Dienst laeuft als non-root (User=${SERVICE_USER}). Ein Bind auf einen
# privilegierten Port (<1024, z.B. 443) scheitert dann mit "permission denied"
# (Feldreport Debian-13-Cloud). CAP_NET_BIND_SERVICE erlaubt genau diesen Bind,
# ohne dem Dienst root-Rechte zu geben. Bei Ports >= 1024 wird keine Capability
# vergeben (least privilege).
if [ "${PORT}" -lt 1024 ]; then
    CAP_AMBIENT="AmbientCapabilities=CAP_NET_BIND_SERVICE"
    CAP_BOUNDING="CapabilityBoundingSet=CAP_NET_BIND_SERVICE"
    info "Port ${PORT} < 1024 -> CAP_NET_BIND_SERVICE wird dem Dienst gewaehrt."
else
    CAP_AMBIENT="# Port ${PORT} >= 1024: keine Capabilities erforderlich"
    CAP_BOUNDING="CapabilityBoundingSet="
fi

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

# Privilegierte Ports (<1024) als non-root binden
${CAP_AMBIENT}
${CAP_BOUNDING}

# Security-Hardening
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${INSTALL_DIR}/data ${INSTALL_DIR}/logs ${INSTALL_DIR}/config
PrivateTmp=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectClock=yes
ProtectHostname=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
SystemCallArchitectures=native

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"

# --- Setup daily backup (systemd-Timer, kein cron noetig) ---
# Frueher via crontab — cron ist auf Minimal-/Cloud-Images (z.B. Debian-13-Cloud)
# nicht installiert ("crontab: command not found", Feldreport). Ein systemd-Timer
# braucht keine zusaetzlichen Pakete und holt verpasste Laeufe nach (Persistent).
info "Richte taegliches Backup ein (systemd-Timer, 02:00)..."
cat > "/etc/systemd/system/${SERVICE_NAME}-backup.service" << BKSVCEOF
[Unit]
Description=PraxisZeit taegliches Backup

[Service]
Type=oneshot
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/bin/python/bin/python3 ${INSTALL_DIR}/praxiszeit-server.py backup
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${INSTALL_DIR}/data ${INSTALL_DIR}/logs
PrivateTmp=yes
BKSVCEOF

cat > "/etc/systemd/system/${SERVICE_NAME}-backup.timer" << BKTMREOF
[Unit]
Description=PraxisZeit taegliches Backup (02:00)

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
BKTMREOF

# Best-effort: einen alten cron-Eintrag frueherer Versionen entfernen (nur wenn
# cron ueberhaupt vorhanden ist) — sonst liefen Backup-Timer und cron doppelt.
if command -v crontab &>/dev/null; then
    ( crontab -u "${SERVICE_USER}" -l 2>/dev/null | grep -v "praxiszeit-server.py backup" || true ) \
        | crontab -u "${SERVICE_USER}" - 2>/dev/null || true
fi

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}-backup.timer"

# --- Start service ---

info "Starte PraxisZeit..."
systemctl start "${SERVICE_NAME}"

# Wait for startup
for i in $(seq 1 30); do
    # Here-String statt `curl | grep -q`: grep -q beendet bei Treffer frueh ->
    # curl SIGPIPE -> mit pipefail wuerde die Bedingung nie wahr (Wait liefe
    # immer volle 30s). So bricht der Wait korrekt ab, sobald healthy.
    if grep -q "healthy" <<<"$(curl -sk "https://localhost:${PORT}/api/health" 2>/dev/null || true)"; then
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
