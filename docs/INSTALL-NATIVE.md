# PraxisZeit Native Installation (ohne Docker)

Anleitung zur Installation von PraxisZeit als Einzelinstanz auf einem Linux-Server ohne Docker.

## Voraussetzungen

- Linux (Ubuntu 22.04+, Debian 12+, Arch, etc.)
- Python 3.12+
- PostgreSQL 16+ (wird automatisch installiert oder system-weit genutzt)
- Node.js 20+ (nur zum Bauen des Frontends)
- OpenSSL (fuer Zertifikat-Generierung)
- 512 MB RAM, 1 GB Festplatte

## Schnellinstallation (System-Pakete)

Nutzt systemweit installiertes Python + PostgreSQL.

```bash
# 1. Repository klonen
git clone https://github.com/phash/praxiszeit.git
cd praxiszeit

# 2. Frontend bauen
cd frontend && npm ci && npm run build && cd ..

# 3. Installer starten
sudo installer/linux/install-local.sh /opt/praxiszeit
```

Der Installer fragt interaktiv nach:
- Praxis-Name
- Admin-E-Mail + Passwort
- HTTP-Port (Standard: 8443)

Nach der Installation:
```bash
sudo systemctl start praxiszeit     # Starten
sudo systemctl status praxiszeit    # Status pruefen
sudo systemctl stop praxiszeit      # Stoppen
journalctl -u praxiszeit -f         # Live-Logs
```

## Produktivinstallation (gebuendelte Binaries)

Fuer Kunden-Server ohne vorinstalliertes Python/PostgreSQL.

```bash
# 1. Release-Paket herunterladen
wget https://releases.praxiszeit.de/praxiszeit-1.2.0-linux-x64.tar.gz

# 2. Entpacken und installieren
tar xzf praxiszeit-1.2.0-linux-x64.tar.gz
cd praxiszeit-1.2.0
sudo ./install.sh
```

Das Release-Paket enthaelt Python 3.12 und PostgreSQL 16 als portable Binaries — keine System-Pakete noetig.

### Release-Paket selber bauen

Das Build-Script laedt Python, PostgreSQL und nssm automatisch herunter:

```bash
# Alles bauen (Linux + Windows)
bash tools/build-release.sh

# Nur Linux
bash tools/build-release.sh --linux-only

# Nur Windows
bash tools/build-release.sh --windows-only

# Bestimmte Version
bash tools/build-release.sh --version 1.3.0

# Cache nutzen (Binaries nicht erneut laden)
bash tools/build-release.sh --skip-download
```

Gebuendelte Binaries (automatisch heruntergeladen):

| Komponente | Linux | Windows |
|------------|-------|---------|
| Python 3.13 | python-build-standalone (indygreg) | python-build-standalone (indygreg) |
| PostgreSQL 16 | EDB Binaries (.tar.gz) | EDB Binaries (.zip) |
| nssm | — | nssm.cc (Service Manager) |

Ergebnis in `dist/`:
- `praxiszeit-X.Y.Z-linux-x64.tar.gz` (~200 MB)
- `praxiszeit-X.Y.Z-windows-x64.zip` (~400 MB)
- `praxiszeit-X.Y.Z-SHA256SUMS.txt`

## Windows-Installation

```
1. ZIP entpacken nach C:\PraxisZeit\
2. setup.bat ausfuehren (installiert Python-Dependencies)
3. install-service.bat ausfuehren (registriert Windows-Dienst)
4. net start PraxisZeit
```

Beim ersten Start:
- PostgreSQL wird automatisch initialisiert
- Datenbank + Benutzer werden erstellt
- Migrationen laufen automatisch
- Admin-Account wird aus der Konfiguration angelegt

## Verzeichnisstruktur

```
/opt/praxiszeit/
├── bin/
│   ├── python/            # Python 3.12 (venv oder portable)
│   └── postgresql/        # PostgreSQL-Binaries (System oder portable)
├── app/
│   ├── backend/           # FastAPI-Quellcode + Alembic-Migrationen
│   └── frontend/          # Gebautes React-Frontend (dist/)
├── data/
│   ├── db/                # PostgreSQL-Datenverzeichnis
│   └── backups/           # Automatische taegliche Backups
├── config/
│   ├── praxiszeit.conf    # Hauptkonfiguration (TOML)
│   ├── license.key        # Lizenzschluessel (optional)
│   └── ssl/               # SSL-Zertifikate
├── logs/
│   └── praxiszeit.log     # Anwendungslog (rotiert, max 50 MB)
├── praxiszeit-server.py   # Process Manager
└── start.sh               # Start-Wrapper
```

## Konfiguration

Die Konfigurationsdatei `config/praxiszeit.conf` im TOML-Format:

```toml
[server]
port = 443
ssl_cert = "config/ssl/cert.pem"
ssl_key = "config/ssl/key.pem"

[practice]
name = "Praxis Dr. Mueller"
holiday_state = "Bayern"

[admin]
username = "admin"
email = "admin@praxis.local"

[security]
login_rate_limit = "5/minute"
cookie_secure = true

[backup]
enabled = true
schedule = "02:00"
retention_days = 31
```

Vollstaendiges Beispiel: `installer/praxiszeit.conf.example`

## Service-Verwaltung

```bash
# Service starten/stoppen
sudo systemctl start praxiszeit
sudo systemctl stop praxiszeit
sudo systemctl restart praxiszeit

# Status
sudo systemctl status praxiszeit

# Logs
journalctl -u praxiszeit -f
cat /opt/praxiszeit/logs/praxiszeit.log

# Manuell starten (Debugging)
sudo -u praxiszeit /opt/praxiszeit/start.sh start
```

## Backup & Restore

Automatische Backups laufen taeglich um 02:00 (konfigurierbar).

```bash
# Manuelles Backup
sudo -u praxiszeit /opt/praxiszeit/start.sh backup

# Backups anzeigen
ls -la /opt/praxiszeit/data/backups/

# Restore
sudo systemctl stop praxiszeit
pg_restore -U praxiszeit -d praxiszeit /opt/praxiszeit/data/backups/praxiszeit_DATUM.sql.gz
sudo systemctl start praxiszeit
```

Aufbewahrung: 31 Tage (ArbZG §16: Mindestens 2 Jahre).

## SSL/HTTPS

```bash
# Selbstsigniertes Zertifikat generieren
openssl req -x509 -newkey ed25519 \
  -keyout /opt/praxiszeit/config/ssl/key.pem \
  -out /opt/praxiszeit/config/ssl/cert.pem \
  -days 3650 -nodes \
  -subj "/CN=PraxisZeit" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:$(hostname -I | awk '{print $1}')"

# In praxiszeit.conf aktivieren
# [server]
# ssl_cert = "config/ssl/cert.pem"
# ssl_key = "config/ssl/key.pem"

sudo systemctl restart praxiszeit
```

## Lizenzierung

```bash
# Lizenzschluessel einspielen
cp license.key /opt/praxiszeit/config/license.key

# In praxiszeit.conf aktivieren
# [license]
# key_file = "config/license.key"

sudo systemctl restart praxiszeit
```

Ohne Lizenz laeuft die Anwendung uneingeschraenkt (Lizenzierung ist optional).

## Deinstallation

```bash
sudo systemctl stop praxiszeit
sudo systemctl disable praxiszeit
sudo rm /etc/systemd/system/praxiszeit.service
sudo systemctl daemon-reload

# Optional: Daten loeschen
sudo rm -rf /opt/praxiszeit
sudo userdel praxiszeit
```

## Fehlerbehebung

| Problem | Loesung |
|---------|---------|
| PostgreSQL startet nicht | `cat /opt/praxiszeit/logs/postgresql-startup.log` |
| Backend startet nicht | `journalctl -u praxiszeit -n 50` |
| Port belegt | Anderen Port in `praxiszeit.conf` setzen |
| Keine Berechtigung | `sudo chown -R praxiszeit:praxiszeit /opt/praxiszeit` |
| Migration fehlgeschlagen | `sudo -u praxiszeit /opt/praxiszeit/start.sh start` manuell starten, Fehler lesen |
