# PraxisZeit Native Installation (ohne Docker)

Anleitung zur Installation von PraxisZeit als Einzelinstanz auf einem Server ohne Docker.
Alle Pakete enthalten Python und PostgreSQL — keine Voraussetzungen noetig.

## Unterstuetzte Plattformen

| Plattform | Architektur | Paket | Groesse |
|-----------|-------------|-------|---------|
| Linux | x86_64 | `praxiszeit-X.Y.Z-linux-x64.tar.gz` | ~200 MB |
| Windows | x86_64 | `praxiszeit-X.Y.Z-windows-x64.zip` | ~400 MB |
| macOS | Intel x86_64 | `praxiszeit-X.Y.Z-macos-x64.tar.gz` | ~360 MB |
| macOS | Apple Silicon (M1-M4) | `praxiszeit-X.Y.Z-macos-arm64.tar.gz` | ~360 MB |

---

## Linux-Installation

```bash
# 1. Herunterladen + entpacken
tar xzf praxiszeit-1.2.0-linux-x64.tar.gz
cd praxiszeit

# 2. Installer starten (als root)
sudo ./install.sh
```

Der Installer fragt interaktiv nach Praxis-Name, Admin-Zugangsdaten und Port.

Nach der Installation:
```bash
sudo systemctl start praxiszeit      # Starten
sudo systemctl stop praxiszeit       # Stoppen
sudo systemctl status praxiszeit     # Status
journalctl -u praxiszeit -f          # Live-Logs
```

**Standardpfad:** `/opt/praxiszeit/`

---

## Windows-Installation

```
1. praxiszeit-1.2.0-windows-x64.zip entpacken nach C:\PraxisZeit\

2. setup.bat als Administrator ausfuehren
   - Installiert PostgreSQL (silent, kein GUI)
   - Installiert Python-Dependencies (braucht einmalig Internet)

3. config\praxiszeit.conf.example nach config\praxiszeit.conf kopieren
   - Praxis-Name, Admin-Email, Admin-Passwort anpassen

4. install-service.bat als Administrator ausfuehren
   - Registriert Windows-Dienst "PraxisZeit"
   - Oeffnet Firewall-Port

5. net start PraxisZeit
```

Service-Verwaltung:
```cmd
net start PraxisZeit          &:: Starten
net stop PraxisZeit           &:: Stoppen
sc query PraxisZeit           &:: Status

type C:\PraxisZeit\logs\praxiszeit.log       &:: Logs
type C:\PraxisZeit\logs\service-stdout.log   &:: Service-Logs
```

Deinstallation: `uninstall-service.bat` ausfuehren (Datenbank wird beibehalten).

---

## macOS-Installation

```bash
# Intel Mac:
tar xzf praxiszeit-1.2.0-macos-x64.tar.gz

# Apple Silicon (M1/M2/M3/M4):
tar xzf praxiszeit-1.2.0-macos-arm64.tar.gz

# Installer starten (als root)
sudo ./install.sh
```

Der Installer fragt interaktiv nach Praxis-Name, Admin-Zugangsdaten und Port.
PostgreSQL wird automatisch aus dem mitgelieferten DMG installiert.

Service-Verwaltung (launchd):
```bash
# Starten
sudo launchctl load /Library/LaunchDaemons/de.praxiszeit.server.plist

# Stoppen
sudo launchctl unload /Library/LaunchDaemons/de.praxiszeit.server.plist

# Logs
cat /usr/local/praxiszeit/logs/stdout.log
tail -f /usr/local/praxiszeit/logs/praxiszeit.log
```

**Standardpfad:** `/usr/local/praxiszeit/`

Deinstallation:
```bash
sudo launchctl unload /Library/LaunchDaemons/de.praxiszeit.server.plist
sudo rm /Library/LaunchDaemons/de.praxiszeit.server.plist
sudo rm -rf /usr/local/praxiszeit   # Optional: Daten loeschen
```

---

## Erster Start (alle Plattformen)

Beim ersten Start passiert automatisch:
1. PostgreSQL-Datenbank wird initialisiert
2. Datenbank-Benutzer werden erstellt (mit Row-Level-Security)
3. Alle Migrationen werden ausgefuehrt
4. Admin-Account wird aus der Konfiguration angelegt
5. Feiertage werden synchronisiert

Danach im Browser oeffnen: `http://localhost:<port>` (oder `https://` mit SSL).

---

## Verzeichnisstruktur

```
/opt/praxiszeit/                  (Linux)
C:\PraxisZeit\                    (Windows)
/usr/local/praxiszeit/            (macOS)
│
├── bin/
│   ├── python/                   # Python 3.13 (gebuendelt)
│   └── postgresql/               # PostgreSQL (gebuendelt oder installiert)
├── app/
│   ├── backend/                  # FastAPI + Alembic-Migrationen
│   └── frontend/                 # React-Frontend (gebautes dist/)
├── data/
│   ├── db/                       # PostgreSQL-Datenverzeichnis
│   └── backups/                  # Automatische taegliche Backups
├── config/
│   ├── praxiszeit.conf           # Hauptkonfiguration (TOML)
│   ├── license.key               # Lizenzschluessel (optional)
│   └── ssl/                      # SSL-Zertifikate (optional)
├── logs/
│   └── praxiszeit.log            # Anwendungslog (rotiert, max 50 MB)
└── praxiszeit-server.py          # Process Manager
```

---

## Konfiguration

Die Datei `config/praxiszeit.conf` im TOML-Format:

```toml
[server]
port = 443
ssl_cert = "config/ssl/cert.pem"    # Leer = kein SSL
ssl_key = "config/ssl/key.pem"

[practice]
name = "Praxis Dr. Mueller"
address = "Musterstr. 1, 80000 Muenchen"
holiday_state = "Bayern"

[admin]
username = "admin"
email = "admin@praxis.local"
# Passwort nur beim Erststart verwendet, danach in DB

[security]
login_rate_limit = "5/minute"
cookie_secure = true                # false fuer HTTP-only

[license]
key_file = "config/license.key"     # Optional

[updates]
check_enabled = true
server_url = "https://updates.praxiszeit.de"

[backup]
enabled = true
schedule = "02:00"
retention_days = 31
```

Vollstaendiges Beispiel: `config/praxiszeit.conf.example`

---

## SSL/HTTPS

```bash
# Selbstsigniertes Zertifikat generieren (10 Jahre)
openssl req -x509 -newkey ed25519 \
  -keyout config/ssl/key.pem \
  -out config/ssl/cert.pem \
  -days 3650 -nodes \
  -subj "/CN=PraxisZeit"

# In praxiszeit.conf eintragen:
# [server]
# ssl_cert = "config/ssl/cert.pem"
# ssl_key = "config/ssl/key.pem"
# + cookie_secure = true in [security]
```

---

## Backup & Restore

Automatische Backups laufen taeglich (konfigurierbar in `[backup] schedule`).

```bash
# Manuelles Backup (Linux/macOS)
sudo -u praxiszeit /opt/praxiszeit/praxiszeit-server.py backup

# Backups anzeigen
ls -la /opt/praxiszeit/data/backups/
```

Aufbewahrung: 31 Tage. ArbZG §16 verlangt 2 Jahre — passen Sie `retention_days` entsprechend an.

---

## Lizenzierung

```bash
# Lizenzschluessel einspielen
cp license.key /opt/praxiszeit/config/license.key

# In praxiszeit.conf:
# [license]
# key_file = "config/license.key"

# Service neu starten
```

Ohne Lizenz laeuft die Anwendung uneingeschraenkt.
Bei abgelaufener Lizenz: Nur-Lese-Modus (Daten bleiben einsehbar und exportierbar).

---

## Release-Pakete selber bauen

Voraussetzungen zum Bauen: Linux mit Python 3.12+, Node.js 20+, curl, rsync, zip.
PostgreSQL-Installer fuer Windows (.exe) und macOS (.dmg) muessen manuell von
[enterprisedb.com](https://www.enterprisedb.com/downloads/postgres-postgresql-downloads)
heruntergeladen und in `~/Downloads/` abgelegt werden.

```bash
# Alle Plattformen bauen
bash tools/build-release.sh

# Einzelne Plattformen
bash tools/build-release.sh --linux-only
bash tools/build-release.sh --windows-only
bash tools/build-release.sh --macos-only

# Versionsnummer setzen
bash tools/build-release.sh --version 1.3.0

# Cache nutzen (Downloads nicht wiederholen)
bash tools/build-release.sh --skip-download
```

Gebuendelte Komponenten:

| Komponente | Linux | Windows | macOS |
|------------|-------|---------|-------|
| Python 3.13 | python-build-standalone | python-build-standalone | python-build-standalone |
| PostgreSQL | System-Binaries | EDB Installer (.exe, silent) | EDB Installer (.dmg, silent) |
| Service Manager | systemd | nssm | launchd |

Ergebnis in `dist/`:
```
praxiszeit-X.Y.Z-linux-x64.tar.gz      ~200 MB
praxiszeit-X.Y.Z-windows-x64.zip       ~400 MB
praxiszeit-X.Y.Z-macos-x64.tar.gz      ~360 MB
praxiszeit-X.Y.Z-macos-arm64.tar.gz    ~360 MB
praxiszeit-X.Y.Z-SHA256SUMS.txt
```

---

## Fehlerbehebung

| Problem | Loesung |
|---------|---------|
| PostgreSQL startet nicht | Logs pruefen: `logs/postgresql-startup.log` |
| Backend startet nicht | Linux: `journalctl -u praxiszeit -n 50` / Windows: `logs\service-stderr.log` / macOS: `logs/stderr.log` |
| Port belegt | Anderen Port in `praxiszeit.conf` setzen |
| Keine Berechtigung | Linux: `sudo chown -R praxiszeit:praxiszeit /opt/praxiszeit` |
| Migration fehlgeschlagen | Process Manager manuell starten, Fehlerausgabe lesen |
| Windows: setup.bat schlaegt fehl | Als Administrator ausfuehren, Internetverbindung pruefen |
| macOS: PostgreSQL-DMG nicht gefunden | PostgreSQL manuell installieren: [postgresapp.com](https://postgresapp.com) |

---

## Schnellinstallation fuer Entwickler (Linux, System-Pakete)

Fuer lokale Tests ohne gebuendelte Binaries:

```bash
git clone https://github.com/phash/praxiszeit.git
cd praxiszeit
cd frontend && npm ci && npm run build && cd ..
sudo installer/linux/install-local.sh /opt/praxiszeit
```

Nutzt systemweit installiertes Python + PostgreSQL statt gebundelter Binaries.
