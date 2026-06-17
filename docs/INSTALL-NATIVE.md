# PraxisZeit Native Installation (ohne Docker)

Anleitung zur Installation von PraxisZeit als Einzelinstanz auf einem Server ohne Docker.
Alle Pakete enthalten Python und PostgreSQL — keine Voraussetzungen noetig.

> **Docker bevorzugt?** Wer lieber mit Docker Compose deployt, nutzt nicht diese
> Native-Pakete, sondern das Docker-Bundle bzw. den Quellcode — siehe
> [INSTALL-DOCKER.md](INSTALL-DOCKER.md).

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
#    Das Tarball entpackt FLACH (kein Top-Level-Ordner) — daher zuerst einen
#    Zielordner anlegen und mit -C dorthin entpacken:
mkdir -p praxiszeit-1.8.10
tar xzf praxiszeit-1.8.10-linux-x64.tar.gz -C praxiszeit-1.8.10
cd praxiszeit-1.8.10

# 2. Installer starten (als root)
sudo ./install.sh
```

> **Hinweis Port 443 / privilegierte Ports:** Der Dienst laeuft als
> non-root-Benutzer. Der Installer vergibt fuer Ports < 1024 automatisch
> `CAP_NET_BIND_SERVICE` in der systemd-Unit — ein Bind auf 443 funktioniert
> damit ohne root. (Aeltere Versionen scheiterten hier mit `permission denied`.)

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
1. praxiszeit-1.8.10-windows-x64.zip entpacken nach C:\PraxisZeit\

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
# Tarball entpackt flach — in einen eigenen Ordner entpacken:
mkdir -p praxiszeit-1.8.10 && cd praxiszeit-1.8.10

# Intel Mac:
tar xzf ../praxiszeit-1.8.10-macos-x64.tar.gz

# Apple Silicon (M1/M2/M3/M4):
tar xzf ../praxiszeit-1.8.10-macos-arm64.tar.gz

# Installer starten (als root)
sudo ./install.sh
```

Der Installer fragt interaktiv nach Praxis-Name, Admin-Zugangsdaten und Port.
PostgreSQL ist im Paket **gebuendelt** (theseus-rs 16) und wird beim ersten Start
automatisch initialisiert — eine separate PostgreSQL-Installation (Homebrew /
Postgres.app) ist **nicht** noetig.

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
# Beta: Lizenzpruefung deaktiviert — kein license.key noetig (derzeit ungenutzt).
key_file = "config/license.key"     # Optional

[updates]
check_enabled = true
server_url = "https://updates.mr-development.de"

[backup]
enabled = true
schedule = "02:00"
retention_days = 31
```

Vollstaendiges Beispiel: `config/praxiszeit.conf.example`

---

## SSL/HTTPS

Der Installer erzeugt beim ersten Start automatisch ein gueltiges,
selbstsigniertes **Server**-Zertifikat (RSA-2048, mit Hostname/IP im SAN) —
Browser akzeptieren es nach einmaliger Ausnahme-Bestaetigung. Nur falls Sie
manuell eines erzeugen oder ein abgelehntes ersetzen wollen:

```bash
# WICHTIG: RSA-2048 + End-Entity-SERVER-Zertifikat. NICHT ed25519 und KEIN
# CA-Cert: Browser (Chrome, Firefox/NSS) lehnen ed25519-TLS-Server-Zertifikate
# und CA-Certs ohne extendedKeyUsage=serverAuth ohne "Erweitert"-Option ab.
SERVER_IP=$(hostname -I | awk '{print $1}')
SAN="DNS:localhost,IP:127.0.0.1"
[ -n "$SERVER_IP" ] && SAN="$SAN,IP:$SERVER_IP"

openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout config/ssl/key.pem -out config/ssl/cert.pem \
  -subj "/O=PraxisZeit/CN=praxiszeit" \
  -addext "subjectAltName=$SAN" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth"

# In praxiszeit.conf eintragen:
# [server]
# ssl_cert = "config/ssl/cert.pem"
# ssl_key = "config/ssl/key.pem"
# + cookie_secure = true in [security]
```

> **Hinweis:** Aeltere Anleitungen zeigten `openssl … -newkey ed25519` — solche
> Zertifikate lehnen Browser hart ab (kein „Erweitert"). In dem Fall mit obigem
> RSA-Befehl neu erzeugen und den Dienst neu starten. Im Docker-Deployment
> uebernimmt `ssl/generate-cert.sh` dasselbe.

---

## Backup & Restore

Automatische Backups laufen taeglich um 02:00. Unter Linux geschieht das ueber
einen **systemd-Timer** (`praxiszeit-backup.timer`) — kein `cron` noetig (das
fehlt auf Minimal-/Cloud-Images wie dem Debian-13-Cloudimage).

```bash
# Timer-Status / naechster Lauf (Linux)
systemctl status praxiszeit-backup.timer
systemctl list-timers praxiszeit-backup.timer

# Backup sofort ausloesen (Linux)
sudo systemctl start praxiszeit-backup.service

# Manuelles Backup (Linux/macOS, direkt)
sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 \
    /opt/praxiszeit/praxiszeit-server.py backup

# Backups anzeigen
ls -la /opt/praxiszeit/data/backups/
```

Aufbewahrung: 31 Tage. ArbZG §16 verlangt 2 Jahre — passen Sie `retention_days` entsprechend an.

---

## Lizenzierung

> **Beta:** Die Lizenzpruefung ist derzeit **deaktiviert**. PraxisZeit laeuft
> waehrend der oeffentlichen Beta **ohne** `license.key` mit vollem
> Funktionsumfang — es ist **kein** Lizenzierungs-Schritt noetig. Ein
> Lizenzmodell wird zu einem spaeteren Zeitpunkt eingefuehrt; Nutzer werden
> rechtzeitig informiert.

---

## Release-Pakete selber bauen

Voraussetzungen zum Bauen: Linux mit Python 3.12+, Node.js 20+, curl, rsync, zip.
PostgreSQL fuer **Linux und macOS** wird beim Build automatisch als
`theseus-rs/postgresql-binaries` 16 geladen (SHA256-verifiziert) — kein manueller
Download noetig. Nur fuer **Windows** wird der EDB-Installer (.exe) gebuendelt
(direkter Link `https://get.enterprisedb.com/postgresql/…-windows-x64.exe`, kein
Webformular); mit `--skip-download` wird der Cache aus `~/Downloads/` genutzt.

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
| PostgreSQL | theseus-rs 16 (gebuendelt) | EDB Installer (.exe, silent) | theseus-rs 16 (gebuendelt) |
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
| macOS: PostgreSQL startet nicht | PG ist gebuendelt (theseus), keine Extra-Installation noetig — Logs pruefen: `logs/postgresql-startup.log` |
| `.db-credentials` fehlt, Dienst startet nicht | Siehe Abschnitt "Disaster Recovery" unten |

---

## Disaster Recovery: verlorene `.db-credentials`

**Problem.** Die Datei `config/.db-credentials` haelt die Passwoerter fuer die
Datenbank-Benutzer `praxiszeit` (Superuser) und `praxiszeit_app` (Anwendung).
Wenn sie geloescht, ueberschrieben oder beschaedigt wird, das Datenverzeichnis
`data/db/` aber noch existiert (mit dem Marker `.praxiszeit-cluster` darin),
kann der Process Manager den Cluster nicht mehr ansprechen — der Cluster ist
seit dem ersten Start scram-gehaertet, und ohne Passwort akzeptiert er weder
`psql` noch `ALTER ROLE`.

**Symptom.** Der Dienst startet nicht. Im Log (`logs/praxiszeit.log` bzw.
`logs/service-stderr.log` auf Windows) steht ab Version 1.5.x eine eindeutige
Fehlermeldung:

```
[ERROR] .db-credentials is missing, but the data directory is already
initialized (PraxisZeit cluster marker present). The cluster is scram-hardened
and cannot be re-bootstrapped without its existing credentials. Recovery
options are documented in docs/INSTALL-NATIVE.md (section 'Disaster Recovery:
verlorene .db-credentials').
```

Bei aelteren Versionen (vor dem Fail-Fast-Branch) hing der Dienststart still
an einem `psql`-Aufruf — auch dort ist die Diagnose dieselbe: Datenverzeichnis
gehoert uns, aber die Credentials fehlen.

**Wann tritt das auf?**

- Aufraeum-Aktion am Server (Backup-Skript loescht `config/` mit)
- Festplatten-Image-Restore, der `config/` aus einem Stand vor dem ersten
  Start zurueckspielt
- Falsch konfigurierter Robocopy-/rsync-Job, der `.dotfiles` nicht mitnimmt
- Manuelles "ich raeume mal auf" — die Datei sieht harmlos aus

### Recovery-Pfad A: Restore aus Backup (bevorzugt)

Wenn ein Backup von `config/.db-credentials` existiert (z.B. aus dem
naechtlichen `data/backups/`-Verzeichnis oder einem externen Backup):

```bash
# Linux/macOS
cp /pfad/zum/backup/.db-credentials /opt/praxiszeit/config/.db-credentials
chmod 600 /opt/praxiszeit/config/.db-credentials
chown praxiszeit:praxiszeit /opt/praxiszeit/config/.db-credentials
sudo systemctl start praxiszeit
```

```cmd
:: Windows (als Administrator)
copy /Y \pfad\zum\backup\.db-credentials C:\PraxisZeit\config\.db-credentials
icacls C:\PraxisZeit\config\.db-credentials /inheritance:r /grant:r "SYSTEM:F" "Administrators:F"
net start PraxisZeit
```

Der Dienst startet, der vorhandene Cluster wird wiederverwendet, alle Daten
bleiben erhalten.

### Recovery-Pfad B: Cluster neu initialisieren (Daten retten via pg_dumpall)

Wenn KEIN Backup der `.db-credentials` existiert, aber die Datenbank inhaltlich
intakt ist und noch erreichbar (z.B. weil der alte Dienst noch laeuft oder
sich `psql` lokal noch peer-authentifizieren kann):

```bash
# 1. Backup ziehen, solange der Cluster noch antwortet
cd /opt/praxiszeit
bin/postgresql/bin/pg_dumpall -U praxiszeit -h localhost > /root/praxiszeit-rescue.sql

# 2. Dienst stoppen
sudo systemctl stop praxiszeit

# 3. Datenverzeichnis komplett entfernen (Marker geht damit auch weg)
sudo rm -rf data/db

# 4. Dienst starten — initdb laeuft neu, frischer Cluster mit neuen Credentials
sudo systemctl start praxiszeit

# 5. Daten zurueckspielen (nach erfolgreichem Start)
bin/postgresql/bin/psql -U praxiszeit -h localhost -f /root/praxiszeit-rescue.sql
```

Windows-Aequivalent:
```cmd
cd C:\PraxisZeit
bin\postgresql\bin\pg_dumpall.exe -U praxiszeit -h localhost > C:\praxiszeit-rescue.sql
net stop PraxisZeit
rd /s /q data\db
net start PraxisZeit
bin\postgresql\bin\psql.exe -U praxiszeit -h localhost -f C:\praxiszeit-rescue.sql
```

### Recovery-Pfad C: Quarantaene (kein Dump moeglich)

Wenn `pg_dumpall` nicht mehr funktioniert (kein Passwort, keine peer-Auth),
das alte Datenverzeichnis aber zur spaeteren forensischen Wiederherstellung
erhalten bleiben soll:

```bash
# 1. Dienst stoppen
sudo systemctl stop praxiszeit

# 2. Marker entfernen — dann sieht der Process Manager das Verzeichnis als
#    "fremd" an und greift die bestehende Quarantaene-Logik
sudo rm /opt/praxiszeit/data/db/.praxiszeit-cluster

# 3. Dienst starten — das alte Datenverzeichnis wird automatisch nach
#    data/db.foreign-<timestamp> verschoben (NICHT geloescht), und ein
#    frischer Cluster mit neuen Credentials wird initialisiert
sudo systemctl start praxiszeit
```

Das alte Verzeichnis bleibt als `data/db.foreign-YYYYMMDD-HHMMSS/` erhalten
und kann spaeter manuell ausgewertet werden (z.B. mit einem gepatchten
`pg_hba.conf` auf `trust`, um Daten herauszuziehen).

Windows-Aequivalent:
```cmd
net stop PraxisZeit
del C:\PraxisZeit\data\db\.praxiszeit-cluster
net start PraxisZeit
```

### Wann ist ein voller Re-Install noetig?

Nur wenn **alle drei Pfade** scheitern: kein Backup der Credentials, kein
funktionierender `pg_dumpall`, und der Quarantaene-Pfad scheitert ebenfalls
(z.B. weil das Datenverzeichnis korrupt ist). In dem Fall:

1. `data/db/` und `config/.db-credentials` loeschen
2. `setup.bat` / `install.sh` erneut ausfuehren
3. Letztes verfuegbares Backup aus `data/backups/` in den frischen Cluster
   einspielen (siehe Abschnitt "Backup & Restore")

### Praevention

- Backup-Job einrichten, der `config/.db-credentials` **mit-sichert** (nicht
  nur `data/db/`)
- Datei-Permissions nicht aendern: `chmod 600` + Eigentuemer `praxiszeit`
- Vor Aufraeum-Aktionen am Server: `config/` ist nicht "Cache", sondern
  Single-Source-of-Truth fuer die DB-Anmeldedaten

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

---

## Build & Release: PostgreSQL-Quelle & macOS-Verifikation (Hintergrund)

*(Ausgelagert aus CLAUDE.md — 1.5.x-Postmortems, hier mit voller Historie.)*

**PostgreSQL-Quelle (ab 1.5.0):** Linux- und macOS-Tarbälle bündeln
`theseus-rs/postgresql-binaries` **16.13.0** (Manylinux-Build, forward-kompatibel
bis **glibc 2.34** → Ubuntu 22.04+, Debian 12+, RHEL/Rocky/Alma 9+, Fedora 35+).
Die früher genutzten **EDB-Tarbälle sind seit 2026-05 nicht mehr verfügbar**
(HTTP 403); der System-PG-Fallback wurde mit **#125** entfernt. `build-release.sh`
bricht hart ab, wenn die Quelle nicht erreichbar ist oder das `postgres`-Binary
glibc-Symbole > 2.34 verlangt (`check_glibc_compat`).

**Integritätsprüfung der PG-Downloads:**
- Linux UND macOS: SHA256-verifiziert (`download_with_sha`).
- macOS zusätzlich: nach `tar xzf` werden `postgres`/`initdb` per `file(1)` als
  **Mach-O** verifiziert. Das ist die **1.5.2-Härtung** und verhindert das
  **1.5.0-Pattern**, bei dem nur das EDB-**DMG** (ohne entpackbare Binaries) im
  Paket landete und der Build trotzdem „erfolgreich" meldete.

**⚠️ macOS-CI-Gap:** `validate-macos.yml` läuft auf dem **privaten** Repo **nicht**
(alle Runs hängen dauerhaft `queued` — keine macOS-Runner-Minuten). 1.8.1–1.8.7
wurden daher **nur** auf Basis der lokalen `file(1)`-Mach-O-Prüfung im Build
ausgeliefert. **Nicht** auf den GH-Workflow warten; echtes macOS-`initdb`-Smoke
ggf. manuell auf einem Mac. `tools/validate-release.sh` (Linux, Docker-Smoke
gegen 4 Distros) muss vor jedem Release grün sein.

**Windows-PG ≠ theseus:** Die `.exe`/`.zip`-Pakete bündeln den **EDB-Installer**
(`postgresql-installer.exe`, PG 18.x); die theseus-16-Binaries gelten nur für die
Linux/macOS-Tarbälle. PG-Windows-Installer direkt (kein Webformular):
`https://get.enterprisedb.com/postgresql/postgresql-X.Y-Z-windows-x64.exe`.
