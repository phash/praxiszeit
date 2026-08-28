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

# #423 (Review 1.17.0): Bricht das Skript zwischen "Dienst fuer Update gestoppt"
# und dem einzigen abschliessenden "systemctl start" (s.u.) ab — z. B. einer der
# vier PG-Major-Upgrade-Exits, ein fehlschlagendes cp/chown/systemctl enable —
# blieb PraxisZeit bisher dauerhaft unten, ohne jeden Hinweis auf den noetigen
# Neustart. EXIT-Trap faengt jeden nicht-0-Abbruch ab, solange der Dienst fuer
# dieses Update tatsaechlich gestoppt wurde, und startet ihn automatisch neu.
# `exit "$rc"` am Ende erzwingt den urspruenglichen Exit-Code unabhaengig davon,
# was systemctl im Trap zurueckliefert (sonst wuerde ein erfolgreicher Neustart
# den echten Fehler-Exitcode ueberschreiben und den Abbruch verschleiern).
SERVICE_WAS_RUNNING=0
_restart_on_abort() {
    local rc=$?
    if [ "$rc" -ne 0 ] && [ "${SERVICE_WAS_RUNNING:-0}" = "1" ]; then
        error "Installation abgebrochen — Dienst wurde fuer das Update gestoppt und wird jetzt automatisch wieder gestartet..."
        if systemctl start "${SERVICE_NAME}" 2>/dev/null; then
            info "Dienst '${SERVICE_NAME}' laeuft wieder."
        else
            error "Automatischer Neustart fehlgeschlagen — bitte manuell ausfuehren: systemctl start ${SERVICE_NAME}"
        fi
    fi
    exit "$rc"
}
trap _restart_on_abort EXIT

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
    # Arch/CachyOS liefern ab libxml2 2.14 nur noch libxml2.so.16.
    # #177: Das Bundle bringt libxml2.so.2 jetzt in bin/postgresql/lib/ mit (PG
    # findet sie via RPATH/LD_LIBRARY_PATH). Daher NUR abbrechen, wenn WEDER das
    # Bundle NOCH das System die .so.2 hat (frueh + klar statt opaker Crash-Loop).
    ldcache=$(ldconfig -p 2>/dev/null || true)   # nach apt/dnf/zypper/pacman neu einlesen
    bundled_libxml2="$(cd "$(dirname "$0")" && pwd)/bin/postgresql/lib/libxml2.so.2"
    if [ ! -f "$bundled_libxml2" ] && ! grep -qE "^[[:space:]]*libxml2\.so\.2\b" <<<"$ldcache"; then
        error "libxml2.so.2 fehlt — weder im Bundle (bin/postgresql/lib/) noch im System."
        error "Vermutlich ein unvollstaendiges Paket auf einer Rolling-Distro (Arch/CachyOS)."
        error "Unterstuetzt: Debian 12+, Ubuntu 22.04+, RHEL/Rocky/Alma 9+ (System-libxml2),"
        error "Rolling-Distros via gebuendelte libxml2.so.2."
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

# #421: Lizenz-Erkennung MUSS vor der Update-Verzweigung stehen. Sie lag frueher
# im Abfrage-Block und wurde damit im Update-Fall uebersprungen -> LICENSE_FILE
# ungesetzt -> `set -u` brach den Installer nach der Zusammenfassung ab.
# Eine license.key neben dem Installer gilt in BEIDEN Faellen.
_PKG_DIR="$(cd "$(dirname "$0")" && pwd)"
LICENSE_FILE=""
if [ -f "${_PKG_DIR}/license.key" ]; then
    LICENSE_FILE="${_PKG_DIR}/license.key"
fi

# #421: Das Zielverzeichnis MUSS vor allen anderen Abfragen feststehen, denn es
# entscheidet, ob dies eine Erstinstallation oder ein Update ist. Frueher wurde
# es erst nach dem Admin-Passwort erfragt — der Betreiber tippte im Update-Lauf
# Praxisdaten und ein Admin-Passwort ein, die der Installer anschliessend
# stillschweigend verwarf (die bestehende praxiszeit.conf bleibt erhalten, siehe
# unten). Wer sich danach mit dem gerade eingegebenen Passwort anmelden wollte,
# bekam ein 401 und musste annehmen, das Update habe sein Konto zerstoert.
read -rp "Installationsverzeichnis [${INSTALL_DIR}]: " CUSTOM_DIR
INSTALL_DIR=${CUSTOM_DIR:-$INSTALL_DIR}

UPDATE_MODE=0
if [ -f "${INSTALL_DIR}/config/praxiszeit.conf" ]; then
    UPDATE_MODE=1
fi

# Werte aus einer bestehenden praxiszeit.conf lesen (nur fuer Anzeige + die
# wenigen Stellen, die sie ausserhalb des Config-Schreibens brauchen: PORT fuer
# CAP_NET_BIND_SERVICE, GEN_SSL fuer die Zertifikatsfrage).
conf_value() {
    sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "${INSTALL_DIR}/config/praxiszeit.conf" 2>/dev/null \
        | head -1 | sed 's/^"//; s/"$//'
}

if [ "$UPDATE_MODE" = "1" ]; then
    echo ""
    info "Bestehende Installation in ${INSTALL_DIR} erkannt -> UPDATE."
    echo ""
    echo "  Konfiguration und Zugangsdaten bleiben unveraendert:"
    echo "  Praxisdaten, Admin-Konto und -Passwort, Port, SSL und der"
    echo "  Sicherheitsschluessel werden NICHT neu abgefragt und NICHT ueberschrieben."
    echo "  Eingespielt werden ausschliesslich Programmcode und Datenbank-Migrationen."
    echo ""
    echo "  Ihr bisheriges Admin-Passwort gilt unveraendert weiter."
    echo ""

    PRACTICE_NAME=$(conf_value name)
    HOLIDAY_STATE=$(conf_value holiday_state)
    ADMIN_USERNAME=$(conf_value username)
    ADMIN_EMAIL=$(conf_value email)
    PORT=$(conf_value port)
    PORT=${PORT:-443}
    # #423: Port aus einer bestehenden praxiszeit.conf war bisher ungeprueft.
    # Ein von Hand ergaenzter Inline-Kommentar (von den eigenen Docs empfohlenes
    # Format, z. B. setup-anleitung.md: "port = 443   # 443 mit SSL, 80 ohne SSL")
    # liesse die spaetere arithmetische Pruefung `[ "$PORT" -lt 1024 ]` mit
    # "Ganzzahl erwartet" scheitern; set -e greift bei if-Bedingungen NICHT ->
    # stiller Fallback auf CapabilityBoundingSet= OHNE CAP_NET_BIND_SERVICE ->
    # Bind auf einen privilegierten Port (z. B. 443) scheitert nach dem Update.
    # Fuehrenden Zahlenwert extrahieren (ignoriert Trailing-Kommentar/Whitespace) —
    # NICHT alle Nicht-Ziffern global entfernen: der Docs-Kommentartext selbst
    # enthaelt Ziffern ("443 mit SSL, 80 ohne SSL"), ein globales Strippen wuerde
    # sie faelschlich an den echten Port anhaengen.
    PORT_RAW="${PORT}"
    PORT=$(printf '%s' "$PORT" | sed -E 's/^[[:space:]]*([0-9]+).*/\1/')
    if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
        error "Port '${PORT_RAW}' aus ${INSTALL_DIR}/config/praxiszeit.conf ist ungueltig — Abbruch."
        exit 1
    fi
    # SSL-Status separat erfassen: GEN_SSL bedeutet hier nur "Zertifikat fehlt und
    # muss neu erzeugt werden", NICHT "SSL ist aktiv" — wird unten fuer den
    # Health-Check + die Abschluss-URL gebraucht (#423, Fund 4).
    if [ -n "$(conf_value ssl_cert)" ]; then
        SSL_ACTIVE=1
        # Zertifikat nur neu erzeugen, wenn die bestehende Installation ueberhaupt
        # SSL nutzt UND das Zertifikat fehlt (sonst bleibt es unangetastet).
        if [ ! -f "${INSTALL_DIR}/config/ssl/cert.pem" ]; then
            GEN_SSL="J"
        else
            GEN_SSL="n"
        fi
    else
        SSL_ACTIVE=0
        GEN_SSL="n"
    fi
else

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

echo ""
read -rp "HTTPS-Port [443]: " PORT
PORT=${PORT:-443}
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    error "Ungueltiger Port '${PORT}'. Erlaubt: 1-65535."
    exit 1
fi

read -rp "Selbstsigniertes SSL-Zertifikat generieren? [J/n]: " GEN_SSL
GEN_SSL=${GEN_SSL:-J}
if [ "${GEN_SSL,,}" = "j" ]; then
    SSL_ACTIVE=1
else
    SSL_ACTIVE=0
fi

fi   # Ende des Erstinstallations-Zweigs (#421)

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
if [ "$UPDATE_MODE" = "1" ]; then
echo "  Modus:       UPDATE (Konfiguration + Zugangsdaten bleiben unveraendert)"
echo "  Praxis:      ${PRACTICE_NAME:-(aus bestehender Konfiguration)}"
echo "  Admin:       ${ADMIN_USERNAME:-(unveraendert)} — Passwort unveraendert"
echo "  Port:        ${PORT}"
echo "  Verzeichnis: ${INSTALL_DIR}"
else
echo "  Praxis:      ${PRACTICE_NAME}"
echo "  Bundesland:  ${HOLIDAY_STATE}"
echo "  Admin:       ${ADMIN_USERNAME} <${ADMIN_EMAIL}>"
echo "  Port:        ${PORT}"
echo "  SSL:         $([ "${GEN_SSL,,}" = "j" ] && echo 'Ja (selbstsigniert)' || echo 'Nein')"
echo "  Verzeichnis: ${INSTALL_DIR}"
fi
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
    # #423: Ab hier greift der EXIT-Trap (s.o.) — jeder Abbruch bis zum
    # abschliessenden systemctl start startet den Dienst automatisch wieder.
    SERVICE_WAS_RUNNING=1
    # Kurze Pause: das als Kind laufende postgres gibt die gemappten Binaries
    # erst nach dem Cgroup-Stop frei (sonst vereinzelt weiter "Text file busy").
    sleep 2
fi

# --- PostgreSQL Major-Upgrade (z. B. 16 -> 18) ---
# PG18-Binaries können ein PG16-Datenverzeichnis NICHT starten (Major-Upgrade ist
# nicht in-place). Daher VOR dem Binary-Tausch mit den ALTEN Binaries dumpen, das
# alte Datenverzeichnis zur Seite legen (NIE löschen) + einen Marker schreiben;
# praxiszeit-server.py spielt den Dump beim ersten Start in den frischen Cluster.
OLD_PGDATA="${INSTALL_DIR}/data/db"
NEW_POSTGRES="${SCRIPT_DIR}/bin/postgresql/bin/postgres"
if [ -f "${OLD_PGDATA}/PG_VERSION" ] && [ -x "${NEW_POSTGRES}" ] && [ -f "${INSTALL_DIR}/config/.db-credentials" ]; then
    OLD_MAJOR=$(cut -d. -f1 "${OLD_PGDATA}/PG_VERSION" 2>/dev/null)
    # awk 'NR==1' statt 'head -1': head schliesst die Pipe frueh -> SIGPIPE +
    # pipefail (CLAUDE.md 1.8.8). Hier zwar kleine Ausgabe, aber konsistent robust.
    NEW_MAJOR=$(LD_LIBRARY_PATH="${SCRIPT_DIR}/bin/postgresql/lib" "${NEW_POSTGRES}" --version 2>/dev/null | grep -oE '[0-9]+' | awk 'NR==1')
    if [ -n "${OLD_MAJOR}" ] && [ -n "${NEW_MAJOR}" ] && [ "${OLD_MAJOR}" -lt "${NEW_MAJOR}" ] 2>/dev/null; then
        info "PostgreSQL-Major-Upgrade ${OLD_MAJOR} -> ${NEW_MAJOR} erkannt — sichere Daten mit den alten Binaries..."
        OLD_PGBIN="${INSTALL_DIR}/bin/postgresql/bin"
        OLD_PGLIB="${INSTALL_DIR}/bin/postgresql/lib"
        RUN_DIR="${INSTALL_DIR}/data/run"
        SU_PW=$(grep -E '^SUPERUSER_PASSWORD=' "${INSTALL_DIR}/config/.db-credentials" | cut -d= -f2-)
        TS=$(date +%Y%m%d_%H%M%S)
        DUMP_FILE="${INSTALL_DIR}/data/backups/pre-upgrade-pg${OLD_MAJOR}-${TS}.sql.gz"
        mkdir -p "${INSTALL_DIR}/data/backups" "${RUN_DIR}"
        chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/data/backups" "${RUN_DIR}" 2>/dev/null || true
        if [ -z "${SU_PW}" ]; then
            error "PG-Upgrade: .db-credentials ohne SUPERUSER_PASSWORD — Migration nicht möglich. Abbruch (Daten unangetastet)."; exit 1
        fi
        # Alten Cluster starten (alte postgresql.conf hat listen_addresses='' +
        # unix_socket_directories bereits gesetzt), dumpen, stoppen — als Dienst-User.
        if ! sudo -u "${SERVICE_USER}" env LD_LIBRARY_PATH="${OLD_PGLIB}" "${OLD_PGBIN}/pg_ctl" -D "${OLD_PGDATA}" -w -t 60 start; then
            error "PG-Upgrade: alter Cluster ließ sich nicht starten — Abbruch (Daten unangetastet)."; exit 1
        fi
        # set -o pipefail im sh -c: sonst maskiert ein erfolgreiches gzip einen
        # mittendrin abgebrochenen pg_dump (partieller, aber valider .gz = Daten-
        # verlust). Bricht jetzt hart ab, wenn pg_dump scheitert.
        if ! sudo -u "${SERVICE_USER}" env LD_LIBRARY_PATH="${OLD_PGLIB}" PGPASSWORD="${SU_PW}" \
                sh -c "set -o pipefail; '${OLD_PGBIN}/pg_dump' -w --clean --if-exists -h '${RUN_DIR}' -U praxiszeit -d praxiszeit | gzip > '${DUMP_FILE}'"; then
            sudo -u "${SERVICE_USER}" env LD_LIBRARY_PATH="${OLD_PGLIB}" "${OLD_PGBIN}/pg_ctl" -D "${OLD_PGDATA}" -w stop 2>/dev/null || true
            rm -f "${DUMP_FILE}"
            error "PG-Upgrade: pg_dump fehlgeschlagen — Abbruch (Daten unangetastet)."; exit 1
        fi
        # Plausibilitaet: ein echter Dump ist nie winzig (selbst leere DB > 1 KB).
        DUMP_SIZE=$(stat -c%s "${DUMP_FILE}" 2>/dev/null || echo 0)
        if [ "${DUMP_SIZE}" -lt 1024 ]; then
            sudo -u "${SERVICE_USER}" env LD_LIBRARY_PATH="${OLD_PGLIB}" "${OLD_PGBIN}/pg_ctl" -D "${OLD_PGDATA}" -w stop 2>/dev/null || true
            rm -f "${DUMP_FILE}"
            error "PG-Upgrade: Dump verdaechtig klein (${DUMP_SIZE} Bytes) — Abbruch (Daten unangetastet)."; exit 1
        fi
        sudo -u "${SERVICE_USER}" env LD_LIBRARY_PATH="${OLD_PGLIB}" "${OLD_PGBIN}/pg_ctl" -D "${OLD_PGDATA}" -w stop 2>/dev/null || true
        # DSGVO Art. 32: der Dump enthält personenbezogene Daten -> nur Owner lesbar
        # (gzip-Redirect legt sonst per umask 0o644/world-readable an).
        chmod 600 "${DUMP_FILE}" 2>/dev/null || true
        # Alte Daten zur Seite legen (NIE löschen) + Marker für praxiszeit-server.py.
        mv "${OLD_PGDATA}" "${INSTALL_DIR}/data/db.pg${OLD_MAJOR}-${TS}"
        echo "${DUMP_FILE}" > "${INSTALL_DIR}/data/.pg-upgrade-restore"
        chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/data/.pg-upgrade-restore" 2>/dev/null || true
        info "Daten gesichert: ${DUMP_FILE}"
        info "Frischer PG${NEW_MAJOR}-Cluster wird beim Start angelegt + Dump eingespielt; alter Cluster bleibt als data/db.pg${OLD_MAJOR}-${TS} erhalten."
    fi
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
if [ -f "${INSTALL_DIR}/config/praxiszeit.conf" ]; then
    # Reinstall/Update: bestehende Konfiguration NICHT ueberschreiben. Ein neu
    # generierter secret_key wuerde sonst alle Sessions ungueltig machen UND alle
    # verschluesselten TOTP-Secrets (Migration 050) unentschluesselbar -> jeder
    # 2FA-Nutzer ausgesperrt. Auch port/SSL/retention/Admin-Passwort des Betreibers
    # bleiben so erhalten. Neue Eingaben aus diesem Lauf werden bewusst ignoriert.
    info "Bestehende config/praxiszeit.conf erkannt -> wird beibehalten (Reinstall/Update)."
else
info "Schreibe Konfiguration..."
# #421: Die TOML-Escapes erst HIER — im Update-Fall sind PRACTICE_NAME/ADMIN_*
# gar nicht abgefragt worden, und `set -u` liess den Installer sonst nach der
# Zusammenfassung abbrechen (Dienst blieb gestoppt).
PRACTICE_NAME_ESC=$(toml_escape "$PRACTICE_NAME")
ADMIN_USERNAME_ESC=$(toml_escape "$ADMIN_USERNAME")
ADMIN_EMAIL_ESC=$(toml_escape "$ADMIN_EMAIL")
ADMIN_PASSWORD_ESC=$(toml_escape "$ADMIN_PASSWORD")
# S1 (Audit 2026-07-31, DSGVO Art. 32): die Datei enthaelt das Admin-Passwort
# und den secret_key (Session-/TOTP-Signaturschluessel). Vorher wurde sie mit
# dem Standard-umask (haeufig 022 -> world-readable 644) angelegt und ERST am
# Skriptende (chmod 600, s.u.) eingeschraenkt — auf einem Mehrbenutzersystem
# war der Klartext in diesem Fenster fuer jeden lokalen User lesbar. umask 077
# in der Subshell erzwingt 600 schon beim Anlegen; das spaetere chmod 600
# bleibt als zweite Absicherung (z.B. Reinstall-Timing) bestehen.
(
umask 077
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
)
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
    # PRACTICE_NAME fuer -subj entschaerfen: ein '/' (z.B. "Dr. Mueller / Partner")
    # zerstoert sonst den RDN-String -> Cert-Erzeugung scheitert -> kein TLS ->
    # Login mit cookie_secure=true bricht. '/' und '\' -> '_', ',' -> ' '.
    _O_NAME=$(printf '%s' "${PRACTICE_NAME}" | tr '/\\' '__' | tr ',' ' ')
    # S1 (Audit 2026-07-31): private key — same "created loose, chmod'd later"
    # window as praxiszeit.conf above. umask 077 in the subshell makes openssl
    # create key.pem (and cert.pem, harmless) as 600 right away; the later
    # `chmod 600 config/ssl/*.pem` stays as a second safeguard.
    if (
        umask 077
        openssl req -x509 -newkey rsa:2048 -keyout "${INSTALL_DIR}/config/ssl/key.pem" \
        -out "${INSTALL_DIR}/config/ssl/cert.pem" -days 3650 -nodes \
        -subj "/CN=PraxisZeit/O=${_O_NAME}" \
        -addext "subjectAltName=${SAN}" \
        -addext "basicConstraints=critical,CA:FALSE" \
        -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
        -addext "extendedKeyUsage=serverAuth"
    ); then
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
# #423: Ab hier ist der Dienst wieder aktiv — der Fund-2-Trap (oben) muss ab hier
# nicht mehr eingreifen. Ein anschliessend fehlschlagender Health-Check (unten)
# ist ein anderes Problem (Fund 4: Migration/Absturz NACH dem Start) als "Dienst
# wurde fuer das Update gestoppt und nie wieder hochgefahren" — ohne den Reset
# wuerde der Trap bei einem Health-Check-Fehlschlag faelschlich melden, der
# Dienst werde wegen des gestoppten Updates neu gestartet, obwohl er laeuft.
SERVICE_WAS_RUNNING=0

# #423: Schema fuer Health-Check + Abschluss-URL aus dem tatsaechlichen
# SSL-Zustand ableiten statt hart https anzunehmen. GEN_SSL bedeutet im
# Update-Zweig nur "Zertifikat fehlt und wird neu erzeugt", NICHT "SSL ist
# aktiv" — SSL_ACTIVE (oben gesetzt) ist die eine Quelle dafuer. Ohne SSL
# spricht der Server Klartext-HTTP; eine hart auf https verdrahtete Probe
# wuerde auf einem voellig gesunden System 30x fehlschlagen.
PROTO="http"
[ "${SSL_ACTIVE}" = "1" ] && PROTO="https"

# Wait for startup. Ergebnis wird jetzt ausgewertet (vorher: $i/Loop-Ausgang
# verworfen, Erfolgsmeldung erschien unbedingt — auch wenn eine fehlgeschlagene
# Migration oder ein PG-Restore-Fehler den frisch gestarteten Dienst Sekunden
# spaeter wieder abstuerzen liess).
HEALTHY=0
for i in $(seq 1 30); do
    # Here-String statt `curl | grep -q`: grep -q beendet bei Treffer frueh ->
    # curl SIGPIPE -> mit pipefail wuerde die Bedingung nie wahr (Wait liefe
    # immer volle 30s). So bricht der Wait korrekt ab, sobald healthy.
    if grep -q "healthy" <<<"$(curl -sk "${PROTO}://localhost:${PORT}/api/health" 2>/dev/null || true)"; then
        HEALTHY=1
        break
    fi
    sleep 1
done

SERVER_IP_SUMMARY=$(hostname -I | awk '{print $1}')

if [ "${HEALTHY}" != "1" ]; then
    echo ""
    echo "=============================================="
    echo -e "  ${YELLOW}PraxisZeit wurde installiert, meldet sich aber nicht${NC}"
    echo "=============================================="
    echo ""
    error "Der Dienst hat innerhalb von 30s keinen 'healthy'-Status unter"
    error "${PROTO}://localhost:${PORT}/api/health gemeldet."
    echo "  Bitte pruefen:"
    echo "    systemctl status ${SERVICE_NAME}"
    echo "    ${INSTALL_DIR}/logs/"
    echo ""
    exit 1
fi

echo ""
echo "=============================================="
if [ "$UPDATE_MODE" = "1" ]; then
    echo -e "  ${GREEN}PraxisZeit erfolgreich aktualisiert!${NC}"
else
    echo -e "  ${GREEN}PraxisZeit erfolgreich installiert!${NC}"
fi
echo "=============================================="
echo ""
echo "  URL:       ${PROTO}://${SERVER_IP_SUMMARY}:${PORT}"
echo "  Admin:     ${ADMIN_USERNAME}"
echo "  Service:   systemctl {start|stop|status} ${SERVICE_NAME}"
echo "  Logs:      ${INSTALL_DIR}/logs/"
echo "  Backups:   ${INSTALL_DIR}/data/backups/"
echo ""
# Der Passwort-Hinweis gilt nur der Erstinstallation — bei einem Update wurde
# gerade kein Passwort gesetzt, und einen "ersten Login" gibt es dort nicht.
# Die Meldung stehenzulassen hiess dem Betreiber etwas zu erzaehlen, das nicht
# passiert ist (Release-Review 1.17.0: die Zusammenfassung muss die Wahrheit
# ueber den tatsaechlichen Ablauf sagen).
if [ "$UPDATE_MODE" = "1" ]; then
    echo "  Konfiguration und Zugangsdaten sind unveraendert geblieben."
else
    echo "  WICHTIG: Aendern Sie das Admin-Passwort nach dem"
    echo "  ersten Login ueber die Benutzerverwaltung!"
fi
echo ""
