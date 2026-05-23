# Setup-Anleitung PraxisZeit

**Aktuelle Version:** 1.4.4 · **Stand:** 23. Mai 2026
Für Linux und Windows · Native Installation und Docker-Deployment

---

## Inhaltsverzeichnis

1. **Einführung** — Was ist PraxisZeit, welche Variante ist die richtige?
2. **Voraussetzungen** — Hardware, Netzwerk, Berechtigungen
3. **Paket besorgen** — GitHub-Releases oder selber bauen
4. **Variante A: Native Installation (Linux)**
5. **Variante B: Native Installation (Windows)**
6. **Variante C: Docker-Deployment (Linux)**
7. **Konfiguration** — `praxiszeit.conf` und `.env`
8. **HTTPS / SSL aktivieren**
9. **Backup & Wiederherstellung** (inkl. § 16 ArbZG)
10. **Updates einspielen**
11. **Erster Login & Onboarding**
12. **Troubleshooting**
13. **Anhang** — Verzeichnisstruktur, Service-Befehle, Support

---

## 1. Einführung

PraxisZeit ist eine **Arbeitszeiterfassung speziell für Arzt- und Therapie-Praxen** mit voller Konformität zum deutschen Arbeitszeitgesetz (ArbZG) und zur DSGVO.

### Welche Installations-Variante wähle ich?

| Kriterium | Native (A/B) | Docker (C) |
|---|---|---|
| Praxis-Server ohne IT-Erfahrung | ✅ empfohlen | — |
| Vorhandener Linux-Server mit Docker-Wissen | — | ✅ empfohlen |
| Updates per Wizard im Browser | ✅ | — |
| Mehrere Instanzen parallel | — | ✅ |
| Windows als Server | ✅ einzige Option | — |
| macOS als Server | ✅ Native | — |
| Cloud-Hosting / Reverse-Proxy davor | — | ✅ |

**Faustregel:** Wer eine eigene Praxis betreibt und nicht selbst Docker administriert, wählt die **Native-Installation**. Wer einen IT-Dienstleister hat oder mehrere Mandanten hosten will, wählt **Docker**.

---

## 2. Voraussetzungen

### Hardware (alle Varianten)

- **CPU:** 2 Kerne (4 empfohlen)
- **RAM:** 2 GB (4 GB empfohlen, ab 10 Mitarbeitenden)
- **Festplatte:** 5 GB frei (DB wächst ca. 50 MB / Mitarbeiter / Jahr)
- **Netzwerk:** Stabile LAN-Verbindung, statische IP empfohlen

### Betriebssystem

| Variante | Empfohlen | Auch unterstützt |
|---|---|---|
| Native Linux | Ubuntu 24.04 / Linux Mint 22 | Debian 12+, Fedora 40+ |
| Native Windows | Windows 11 / Server 2022 | Windows 10 (22H2), Server 2019 |
| Native macOS | macOS 14+ (Sonoma) | macOS 13 (Ventura) |
| Docker | Ubuntu 24.04 / Linux Mint 22 | jede Linux-Distro mit Docker Engine ≥ 24 |

### Berechtigungen

- **Linux/macOS:** Lokaler Benutzer mit `sudo`-Recht (für Installation)
- **Windows:** Administrator-Konto (für Installation und Dienst-Registrierung)

### Netzwerk-Ports

| Port | Wofür | Standard offen? |
|---|---|---|
| 80 (HTTP) | optional, Browser im LAN ohne SSL | Firewall öffnen |
| 443 (HTTPS) | empfohlen, verschlüsselter Zugriff | Firewall öffnen |
| 5432 | PostgreSQL (intern) | **NICHT** nach außen öffnen |

---

## 3. Paket besorgen

Es gibt drei Wege zum Installations-Paket — die Wahl hängt von der Plattform ab.

### 3.1 Verfügbarkeits-Matrix (Stand: 1.4.4)

| Plattform | GitHub-Release verfügbar? | Empfehlung |
|---|---|---|
| **Windows x64** | ✅ Ja (`v1.3.5`, `v1.3.6`) | Download von Releases-Seite (siehe 3.2) |
| **Linux x64** | ❌ Aktuell **kein** Linux-Asset in den Releases | Selber bauen (siehe 3.4) **ODER** Docker (Variante C) |
| **macOS x64 / arm64** | ❌ Aktuell **kein** macOS-Asset | Selber bauen (siehe 3.4) |
| **Docker** | — (kein Paket nötig) | Repository klonen (siehe Variante C, Kapitel 6) |

> **Hinweis:** Die aktuellste GitHub-Release ist v1.3.6 (Windows-only). Der `master`-Branch ist auf v1.4.4 — neuere Features (z. B. 24-Wochen-Ausgleichsreport, vacation-request-edit) sind nur per Build-from-Source verfügbar, bis ein neuer Release-Tag gesetzt wird.

### 3.2 Windows: Direkter Download aus GitHub-Releases

```powershell
# Per Browser:
https://github.com/phash/praxiszeit/releases/latest

# Oder per gh CLI:
gh release download --repo phash/praxiszeit --pattern 'praxiszeit-*-windows-x64.zip' --pattern 'praxiszeit-*-SHA256SUMS.txt'
```

Prüfsumme verifizieren (PowerShell):
```powershell
Get-FileHash praxiszeit-1.3.6-windows-x64.zip -Algorithm SHA256
# Vergleichen mit Inhalt von praxiszeit-1.3.6-SHA256SUMS.txt
```

### 3.3 Linux/macOS: Repository klonen

Da aktuell keine Linux-/macOS-Releases auf GitHub liegen, ist der **Build-from-Source** der einzige Weg für die Native-Installation. Wer den Aufwand vermeiden möchte, nutzt die **Docker-Variante** (Kapitel 6) — sie braucht kein Native-Paket.

### 3.4 Selber bauen (Linux/macOS oder neuere Versionen als Release)

```bash
git clone https://github.com/phash/praxiszeit.git
cd praxiszeit

# Hilfe anzeigen
bash tools/build-release.sh --help

# Linux-Paket bauen
bash tools/build-release.sh --linux-only --version 1.4.4

# Ergebnis in dist/
ls -lh dist/praxiszeit-1.4.4-linux-x64.tar.gz
```

Voraussetzungen für den Eigen-Build:
- Linux mit Python 3.12+, Node.js 20+, `curl`, `rsync`, `zip`
- Etwa **3 GB freier Speicher** während des Builds (PostgreSQL-Binaries, Python-Standalone, Node-Modules)
- Bei macOS- oder Windows-Cross-Build: PostgreSQL-Installer müssen manuell von <https://www.enterprisedb.com/downloads/postgres-postgresql-downloads> in `~/Downloads/` abgelegt werden
- Frontend-Version in `frontend/package.json` muss zur `--version` passen, sonst bricht der Build mit „Version-Drift" ab. Bei Drift: `cd frontend && npm version 1.4.4 --no-git-tag-version`

> **Build-Exit-Code 1 am Ende ist kosmetisch** (letzte Zeile schreibt einen False-Wert); Erfolg = `dist/praxiszeit-X.Y.Z-linux-x64.tar.gz` existiert.

---

## 4. Variante A: Native Installation (Linux)

### 4.1 Paket entpacken und Installer starten

Voraussetzung: das `praxiszeit-<VERSION>-linux-x64.tar.gz` aus Kapitel 3.4 (selber gebaut) liegt vor.

```bash
tar xzf praxiszeit-1.4.4-linux-x64.tar.gz   # <VERSION> entsprechend anpassen
cd praxiszeit
sudo ./install.sh
```

### 4.2 Interaktive Konfiguration

Der Installer ist **vollständig interaktiv** und fragt der Reihe nach ab:

| Frage | Beispiel-Eingabe | Hinweis |
|---|---|---|
| `Praxis-Name:` | `Praxis Dr. Müller` | Pflicht, nicht leer |
| `Bundesland [2]:` | `2` (Bayern) | Auswahl 1–16 (Liste wird gezeigt) |
| `Admin-Benutzername [admin]:` | `admin` | Default ist `admin` |
| `Admin-E-Mail:` | `admin@praxis.local` | Pflicht |
| `Admin-Passwort (min. 12 Zeichen):` | `********` | Mindestens 12 Zeichen, **kein** Komplexitäts-Check (nur Längencheck) |
| `Passwort wiederholen:` | `********` | Muss übereinstimmen |
| `Lizenzschluessel-Datei:` | leer oder Pfad | Kann später nachgereicht werden |
| `HTTPS-Port [443]:` | `443` | Default-Port ist HTTPS:443 |
| `Selbstsigniertes SSL-Zertifikat generieren? [J/n]:` | `J` | Erzeugt sofort ed25519-Cert (10 Jahre) |
| `Installationsverzeichnis [/opt/praxiszeit]:` | leer = Default | Frei wählbar |

Anschließend wird eine **Zusammenfassung** angezeigt und mit `J/n` bestätigt.

### 4.3 Was der Installer tut

- Legt den Systembenutzer `praxiszeit` an
- Erzeugt die Verzeichnisse `bin/`, `app/`, `data/db/`, `data/backups/`, `config/ssl/`, `logs/`
- Generiert kryptographisch sicheren `SECRET_KEY` (256-bit)
- Schreibt `config/praxiszeit.conf` mit `chmod 600` (Owner-only-Lesen)
- Generiert optional selbstsigniertes SSL-Zertifikat
- Registriert systemd-Service `praxiszeit.service`
- Richtet täglichen **Backup-Cron um 02:00** ein (per `crontab -u praxiszeit`)
- Startet den Dienst und wartet auf den Health-Check

### 4.4 Service-Verwaltung

```bash
sudo systemctl start praxiszeit            # Starten
sudo systemctl stop praxiszeit             # Stoppen
sudo systemctl restart praxiszeit          # Neustart
sudo systemctl status praxiszeit           # Status
sudo systemctl enable praxiszeit           # Autostart aktivieren (Default: an)
journalctl -u praxiszeit -f                # Live-Log
```

### 4.5 Im Browser öffnen

Der Installer zeigt die URL am Ende der Installation an, typisch:

```
https://<server-ip>:443
```

Server-IP herausfinden:
```bash
hostname -I
```

> **Bei selbstsigniertem Zertifikat** zeigt der Browser einmalig eine Sicherheitswarnung — bestätigen, danach läuft die Verbindung verschlüsselt.

---

## 5. Variante B: Native Installation (Windows)

> Ab Version 1.4.0 ist alternativ ein grafischer **Setup-Wizard (Avalonia)** in `installer/setup/` verfügbar. Die folgende Anleitung beschreibt den klassischen Batch-Installer, der von Praxis-Servern aus der `.zip` direkt nutzbar ist.

### 5.1 Paket herunterladen und entpacken

1. Aktuellste `praxiszeit-<VERSION>-windows-x64.zip` von <https://github.com/phash/praxiszeit/releases/latest> herunterladen (Stand 23.05.2026: v1.3.6)
2. **Rechtsklick** auf die ZIP → **Eigenschaften** → Häkchen bei **„Zulassen"** setzen (entfernt SmartScreen-Blockade)
3. Entpacken nach `C:\PraxisZeit\` (NICHT `C:\Program Files\` — dort verweigert UAC Schreibzugriffe an die Daten-Subdirs)

### 5.2 `setup.bat` als Administrator ausführen

Eingabeaufforderung als Administrator öffnen (Rechtsklick → „Als Administrator ausführen"):

```cmd
cd C:\PraxisZeit
setup.bat
```

Das Script läuft **nicht-interaktiv** und erledigt automatisch:

1. **PostgreSQL-Erkennung:** Sucht in Registry + `%ProgramFiles%\PostgreSQL\{14..18}` nach bestehender Installation
   - Major ≥ 16 vorhanden → wird per `mklink /J` ins Bundle-Verzeichnis verlinkt
   - Sonst: still installiert PostgreSQL 16.8 aus dem EDB-Installer mit zufälligem 32-Zeichen-Initialpasswort (wird sofort danach durch ein `secrets.token_hex(32)`-generiertes Passwort ersetzt)
2. **Python-Setup:** Bootstrap von `pip`, Installation aller Abhängigkeiten aus `requirements.txt`
3. **Konfigurationsdatei:** Kopiert `config\praxiszeit.conf.example` nach `config\praxiszeit.conf` (falls nicht vorhanden)

### 5.3 Konfiguration anpassen

> **⚠️ Niemals mit Notepad speichern, wenn UTF-8-BOM aktiv ist** — das bricht das TOML-Parsing. **VS Code** oder **Notepad++** mit Kodierung „UTF-8 ohne BOM" verwenden.

```cmd
notepad++ config\praxiszeit.conf
```

Mindestens folgende Werte anpassen:

```toml
[practice]
name = "Praxis Dr. Müller"
holiday_state = "Bayern"

[admin]
username = "admin"
email = "admin@praxis.local"
password = "BITTE_AENDERN_min12zeichen"     # nur Erststart, danach in DB gehasht
first_name = "Admin"
last_name = "Praxis"

[server]
port = 443      # 443 mit SSL, 80 ohne SSL
```

### 5.4 Dienst registrieren und starten

```cmd
install-service.bat
net start PraxisZeit
```

Status prüfen:
```cmd
sc query PraxisZeit
type C:\PraxisZeit\logs\praxiszeit.log
```

Browser öffnen: `https://localhost:443` oder `https://<server-ip>:443` (bzw. ohne SSL `http://...:80`).

### 5.5 Windows-Spezifika beachten

- **Firewall:** `install-service.bat` öffnet automatisch den konfigurierten Port. Bei späterer Port-Änderung manuell freigeben: `netsh advfirewall firewall add rule name="PraxisZeit" dir=in action=allow protocol=TCP localport=8080`
- **Autostart:** Der Dienst startet beim Booten automatisch (`Startup type: Automatic`)
- **Updates:** Über den integrierten Update-Wizard im Browser (Admin → Updates) oder durch erneutes Ausführen von `setup.bat` mit neuem Paket
- **Deinstallation:** `uninstall-service.bat` (Datenbank bleibt erhalten); für komplette Entfernung inkl. Daten anschließend `uninstall.bat`

---

## 6. Variante C: Docker-Deployment (Linux Mint 22 / Ubuntu 24.04)

### 6.1 Docker installieren

```bash
sudo apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null

sudo apt update
sudo apt install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu noble stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker $USER
# WICHTIG: ab- und wieder anmelden, damit die Gruppen-Mitgliedschaft greift

docker --version
docker compose version
```

### 6.2 Repository klonen

```bash
cd ~
git clone https://github.com/phash/praxiszeit.git
cd praxiszeit
```

### 6.3 `.env` anlegen (KORREKTE Variante)

> **⚠️ Sicherheit:** Vor dem Erststart **alle** Passwörter und den `SECRET_KEY` durch eigene Zufallswerte ersetzen.

```bash
POSTGRES_PW=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)
APP_DB_PW=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)
GRAFANA_PW=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)
SECRET=$(python3 -c "import secrets; print(secrets.token_hex(64))")

cat > .env << EOF
# ====== Datenbank ======
POSTGRES_USER=praxiszeit
POSTGRES_PASSWORD=$POSTGRES_PW
POSTGRES_DB=praxiszeit

# App-User für RLS-Enforcement (kein Superuser)
APP_DB_USER=praxiszeit_app
APP_DB_PASSWORD=$APP_DB_PW

# ====== Backend / Security ======
ENVIRONMENT=production
DEPLOYMENT_MODE=onprem
SECRET_KEY=$SECRET
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
COOKIE_SECURE=false                # auf true setzen sobald HTTPS aktiv ist
CORS_ORIGINS=http://localhost
LOGIN_RATE_LIMIT=5/minute
REFRESH_RATE_LIMIT=10/minute

# ====== Praxis-Stammdaten (Excel-Export-Header, DSGVO F-016) ======
PRACTICE_NAME=Praxis Dr. Müller
PRACTICE_ADDRESS=Musterstr. 1, 80000 München
HOLIDAY_STATE=Bayern

# ====== Initialer Admin (nur Erststart) ======
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@praxis.local
ADMIN_PASSWORD=Bitte-Aendern-12Zeichen!
ADMIN_FIRST_NAME=Dr.
ADMIN_LAST_NAME=Müller

# ====== Monitoring ======
GRAFANA_ADMIN_PASSWORD=$GRAFANA_PW
EOF

chmod 600 .env
```

> **Warum `ENVIRONMENT=production`?** Deaktiviert Swagger/ReDoc und macht den Weak-Password-Check zum Hard-Failure.
> **Warum `COOKIE_SECURE=false` zu Beginn?** Beim Erststart ohne HTTPS würde der Browser sonst das Refresh-Cookie verwerfen → kein Login. Nach SSL-Aktivierung (Kapitel 8) auf `true` setzen.

### 6.4 Starten

```bash
docker compose up -d
```

Erststart dauert 3–5 Minuten (Image-Build + DB-Init). Fortschritt verfolgen:
```bash
docker compose logs -f
```

Gesundheits-Check:
```bash
docker compose ps                                    # alle 5 Container sollten "Up" sein
curl http://localhost/api/health
# {"status":"healthy","database":"connected"}
curl http://localhost/api/system/info
# {"deployment_mode":"onprem","version":"1.4.4"}
```

### 6.5 Im LAN erreichbar machen

```bash
sudo ufw allow 80/tcp        # falls ufw aktiv
hostname -I                  # Server-IP anzeigen
```

Andere Geräte im Netz öffnen `http://<server-ip>` im Browser.

---

## 7. Konfiguration

### 7.1 Native: `config/praxiszeit.conf` (TOML)

```toml
[server]
port = 443
ssl_cert = "config/ssl/cert.pem"     # leer = kein SSL
ssl_key  = "config/ssl/key.pem"

[database]
data_dir = "data/db"
superuser = "praxiszeit"             # Superuser für Migrationen
app_user = "praxiszeit_app"          # RLS-User für Runtime

[practice]
name = "Praxis Dr. Müller"
address = "Musterstr. 1, 80000 München"
holiday_state = "Bayern"

[admin]
username = "admin"
email = "admin@praxis.local"
password = "BITTE_AENDERN_min12zeichen"
first_name = "Admin"
last_name = "Praxis"

[security]
# secret_key = ""                     # leer = auto-generiert in config/.secret-key
login_rate_limit = "5/minute"
cookie_secure = true                  # MUSS false sein, wenn ohne SSL!

[license]
key_file = "config/license.key"       # optional, Ed25519-signiert

[updates]
check_enabled = true
server_url = "https://updates.praxiszeit.de"
check_interval_hours = 12

[backup]
enabled = true
schedule = "02:00"
retention_days = 730                  # § 16 ArbZG: min. 2 Jahre!
```

> **Achtung:** Nach jeder Änderung an `praxiszeit.conf` Dienst neu starten (`sudo systemctl restart praxiszeit` bzw. `net stop/start PraxisZeit`).

### 7.2 Docker: `.env`-Variablen

| Variable | Pflicht | Default | Erklärung |
|---|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | ✅ | — | Superuser für Migrationen |
| `APP_DB_USER` / `APP_DB_PASSWORD` | ✅ | — | Runtime-User mit RLS-Enforcement |
| `SECRET_KEY` | ✅ | — | ≥ 64 Hex-Zeichen, niemals defaulten |
| `ENVIRONMENT` | ✅ | (Pflicht) | `production` deaktiviert Swagger + härtet Pwd-Check |
| `DEPLOYMENT_MODE` | — | `onprem` | `saas` nur für gehostete Mandanten |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | — | 30 | Access-Token-Lebensdauer |
| `REFRESH_TOKEN_EXPIRE_DAYS` | — | 7 | Refresh-Token-Lebensdauer |
| `COOKIE_SECURE` | — | true | `false` für HTTP-only Erststart |
| `CORS_ORIGINS` | — | `http://localhost,http://localhost:5173` | Komma-Liste erlaubter Origins |
| `LOGIN_RATE_LIMIT` / `REFRESH_RATE_LIMIT` | — | `5/minute` / `10/minute` | Rate-Limits |
| `PRACTICE_NAME` / `PRACTICE_ADDRESS` / `HOLIDAY_STATE` | — | „Praxis" / leer / Bayern | Excel-Export-Header + Feiertage |
| `ADMIN_USERNAME` / `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_FIRST_NAME` / `ADMIN_LAST_NAME` | ✅ (Email + Pwd) | admin / — / — / Admin / Praxis | Initial-Admin (nur Erststart) |
| `GRAFANA_ADMIN_PASSWORD` | ✅ | — | Pflicht-Variable (sonst startet Stack nicht) |

---

## 8. HTTPS / SSL aktivieren

### 8.1 Variante A/B (Native)

Bei der Linux-Installation wird das Zertifikat optional schon vom Installer generiert (`Selbstsigniertes SSL-Zertifikat generieren? [J/n]`). Manuell nachholen:

```bash
sudo -u praxiszeit openssl req -x509 -newkey ed25519 \
  -keyout /opt/praxiszeit/config/ssl/key.pem \
  -out    /opt/praxiszeit/config/ssl/cert.pem \
  -days 3650 -nodes \
  -subj "/CN=PraxisZeit/O=Praxis Dr. Müller" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:$(hostname -I | awk '{print $1}')"
```

In `praxiszeit.conf`:
```toml
[server]
port = 443
ssl_cert = "config/ssl/cert.pem"
ssl_key  = "config/ssl/key.pem"

[security]
cookie_secure = true
```

Dann: `sudo systemctl restart praxiszeit`.

> **Windows:** identisches Vorgehen — `openssl.exe` liegt im Bundle unter `C:\PraxisZeit\bin\postgresql\bin\openssl.exe`.

### 8.2 Variante C (Docker)

```bash
cd ~/praxiszeit
chmod +x ssl/generate-cert.sh
./ssl/generate-cert.sh                            # erkennt Server-IP automatisch

# COOKIE_SECURE auf true setzen
sed -i 's/^COOKIE_SECURE=false/COOKIE_SECURE=true/' .env

docker compose down
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d

sudo ufw allow 443/tcp
```

Browser öffnet einmalig die Sicherheitswarnung (selbstsigniert) — bestätigen.

**Für „echte" Zertifikate** (Let's Encrypt mit Caddy als Reverse-Proxy): siehe `docs/INFRASTRUCTURE.md` im Repo.

---

## 9. Backup & Wiederherstellung

### 9.1 § 16 ArbZG — Pflichten kurzgefasst

Arbeitgeber müssen Arbeitszeiten **mindestens 2 Jahre** revisionssicher aufbewahren. Verstöße: Bußgeld bis 30.000 €. Diese Pflicht liegt beim Arbeitgeber — PraxisZeit liefert die Werkzeuge, nicht die Aufbewahrung selbst.

### 9.2 Automatische Backups (Native)

Sind ab Werk aktiviert. Der Installer registriert einen Cron-Job:
```bash
sudo crontab -u praxiszeit -l
# 0 2 * * * /opt/praxiszeit/bin/python/bin/python3 /opt/praxiszeit/praxiszeit-server.py backup
```

Retention erhöhen für ArbZG-Konformität:
```toml
# config/praxiszeit.conf
[backup]
enabled = true
schedule = "02:00"
retention_days = 730       # 2 Jahre
```

Backup manuell triggern:
```bash
# Linux/macOS
sudo -u praxiszeit /opt/praxiszeit/praxiszeit-server.py backup

# Windows
cd C:\PraxisZeit
bin\python\python.exe praxiszeit-server.py backup
```

### 9.3 Backups (Docker)

```bash
# Manuell
docker compose exec db pg_dump -U praxiszeit praxiszeit \
  | gzip > ~/backups/praxiszeit_$(date +%Y%m%d).sql.gz

# Täglich per Cron (2:00 Uhr, 730-Tage-Rotation für § 16)
mkdir -p ~/backups
crontab -e
# Zeile anhängen:
0 2 * * * cd ~/praxiszeit && docker compose exec -T db pg_dump -U praxiszeit praxiszeit | gzip > ~/backups/praxiszeit_$(date +\%Y\%m\%d).sql.gz && find ~/backups -name "praxiszeit_*.sql.gz" -mtime +730 -delete
```

### 9.4 Wiederherstellung

**Native (Windows):** `restore-backup.bat` aus dem Installer-Verzeichnis ausführen (fordert die Eingabe „LOESCHEN" zur Bestätigung).

**Native (Linux/macOS):**
```bash
sudo systemctl stop praxiszeit
gunzip -c /opt/praxiszeit/data/backups/<dump>.sql.gz \
  | sudo -u praxiszeit /opt/praxiszeit/bin/postgresql/bin/psql -d praxiszeit
sudo systemctl start praxiszeit
```

**Docker:**
```bash
gunzip -c ~/backups/praxiszeit_20260214.sql.gz \
  | docker compose exec -T db psql -U praxiszeit praxiszeit
```

### 9.5 Compliance-Checkliste

- [ ] Automatisches tägliches Backup eingerichtet
- [ ] Retention ≥ 2 Jahre (730 Tage)
- [ ] Backup-Ablage **außerhalb** des Servers (NAS, externe HDD, verschlüsselter Cloud-Bucket)
- [ ] Mindestens 1× pro Quartal Wiederherstellung getestet
- [ ] Excel-Exporte werden ebenfalls 2 Jahre archiviert
- [ ] Verantwortliche Person für Backup-Monitoring benannt

---

## 10. Updates einspielen

### 10.1 Native (alle Plattformen)

**Variante 1 — Update-Wizard im Browser** (empfohlen):
1. Im Browser einloggen als Admin
2. Menü → **Einstellungen → Updates**
3. „Nach Updates suchen" → falls verfügbar: „Update installieren"
4. Dienst startet automatisch neu, **Browser-Hard-Refresh** (`Strg + F5`) nicht vergessen

**Variante 2 — Neues Paket manuell:**
```bash
# Linux (NEW_VERSION = die neue Versionsnummer)
NEW_VERSION=1.4.5
sudo systemctl stop praxiszeit
tar xzf praxiszeit-${NEW_VERSION}-linux-x64.tar.gz \
  -C /opt/praxiszeit --strip-components=1 \
  --exclude='config' --exclude='data'
sudo systemctl start praxiszeit

# Windows (in cmd als Administrator)
net stop PraxisZeit
:: ZIP entpacken über C:\PraxisZeit\ — config\ und data\ NICHT überschreiben
net start PraxisZeit
```

> **Wichtig:** `config/` und `data/` dürfen nie überschrieben werden — sonst gehen Stammdaten, Backups und der `SECRET_KEY` verloren. Der `--exclude`-Schalter im `tar`-Befehl bzw. selektives Entpacken sind Pflicht.

### 10.2 Docker

```bash
cd ~/praxiszeit
git pull
docker compose down
# Ohne SSL:
docker compose up -d --build
# Mit SSL:
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build
```

DB-Migrationen laufen automatisch beim Backend-Start (über den Superuser via `DATABASE_URL_MIGRATIONS`).

### 10.3 Nach jedem Update

- **Browser:** Hard-Refresh (`Strg + F5`) oder Service-Worker im DevTools deregistrieren — sonst bleibt der alte JS-Code im Cache
- **Version verifizieren:** `curl http://localhost/api/system/info` muss die neue Version zeigen
- **Backend-Health:** `curl http://localhost/api/health` → `{"status":"healthy",...}`

---

## 11. Erster Login & Onboarding

1. `https://<server-ip>` (bzw. `http://...` ohne SSL) im Browser öffnen
2. Login mit Admin-Daten aus Installer / `.env`
3. **Pflicht:** Admin-Passwort sofort unter `Profil → Passwort ändern` neu setzen
4. Praxis-Daten vervollständigen: `Einstellungen → Praxis`
5. Erste Mitarbeitenden anlegen: `Mitarbeiter → Neu`
6. Wöchentliche Soll-Stunden, Urlaubsanspruch und Vertragsbeginn pro Person eintragen
7. Test-Stempelung über `Stempeluhr` → kontrollieren, dass Eintrag in „Heute" erscheint

**Onboarding-Tipp:** Mitarbeitende per Magic-Link einladen (`Mitarbeiter → Einladen`) — sie setzen das Passwort selbst, der Admin lernt das Mitarbeiter-Passwort nie.

---

## 12. Troubleshooting

| Problem | Diagnose | Lösung |
|---|---|---|
| Browser zeigt „Seite nicht erreichbar" | `curl http://localhost/api/health` schlägt fehl | Service-Status prüfen, Logs lesen, ggf. Firewall öffnen |
| `setup.bat` bricht mit Syntaxfehler ab | Windows | Eingabeaufforderung als Administrator starten |
| Login funktioniert, aber Stempeluhr lädt nicht | Browser-Konsole zeigt 405 | Hard-Refresh, ggf. Service-Worker deregistrieren |
| „Network Error" trotz SSL-Setup | Docker | `-f docker-compose.ssl.yml` beim `up -d` vergessen |
| Backend-Container startet nicht | `docker compose logs backend` zeigt `APP_DB_PASSWORD missing` | `.env` aktualisieren, ggf. an `.env.example` orientieren |
| Stack startet gar nicht: `GRAFANA_ADMIN_PASSWORD must be set` | Docker | `GRAFANA_ADMIN_PASSWORD` in `.env` setzen |
| Stack startet nicht: `ENVIRONMENT must be set` | Docker | `ENVIRONMENT=production` (oder `development`) in `.env` setzen |
| Login schlägt mit „kein Cookie" fehl | Ohne SSL | `COOKIE_SECURE=false` in `.env` setzen (Docker) bzw. `cookie_secure = false` in `praxiszeit.conf` (Native) |
| Migration schlägt fehl | `journalctl -u praxiszeit -n 100` | Datenbank-Verbindung prüfen, ggf. Backup zurückspielen |
| Frontend zeigt alte Version nach Update | Browser-Cache | Hard-Refresh `Strg + F5`, Cache leeren |
| `praxiszeit.conf` wird nicht gelesen | Windows | Notepad hat UTF-8-BOM geschrieben — mit VS Code/Notepad++ als „UTF-8 ohne BOM" neu speichern |
| `setup.bat` will PG neu installieren obwohl schon vorhanden | Windows | Existierende PG-Installation muss Major-Version ≥ 16 sein |
| Excel-Export hat falschen Praxis-Header | Docker | `PRACTICE_NAME` / `PRACTICE_ADDRESS` in `.env` setzen und `docker compose up -d` |

### Logs sammeln (für Support)

**Linux Native:**
```bash
sudo journalctl -u praxiszeit -n 500 > praxiszeit-log.txt
sudo tar czf praxiszeit-support.tar.gz \
  /opt/praxiszeit/logs /opt/praxiszeit/config/praxiszeit.conf praxiszeit-log.txt
```

**Windows Native:**
```cmd
cd C:\PraxisZeit\logs
powershell Compress-Archive *.log ..\praxiszeit-support.zip
```

**Docker:**
```bash
cd ~/praxiszeit
docker compose logs --tail=500 > praxiszeit-log.txt
docker compose ps > praxiszeit-status.txt
```

---

## 13. Anhang

### 13.1 Verzeichnisstruktur (Native)

```
/opt/praxiszeit/                  (Linux)
C:\PraxisZeit\                    (Windows)
/usr/local/praxiszeit/            (macOS)
│
├── bin/
│   ├── python/                   Python 3.13 (gebündelt)
│   └── postgresql/               PostgreSQL 16 (gebündelt oder Junction)
├── app/
│   ├── backend/                  FastAPI + Alembic
│   └── frontend/                 React (kompiliert)
├── data/
│   ├── db/                       PostgreSQL-Daten
│   └── backups/                  tägliche Backups
├── config/
│   ├── praxiszeit.conf           Hauptkonfiguration (chmod 600)
│   ├── .secret-key               (auto-generiert, NICHT löschen!)
│   ├── license.key               (optional)
│   └── ssl/                      SSL-Zertifikate
├── logs/
│   └── praxiszeit.log            rotiert, max. 50 MB
└── praxiszeit-server.py          Prozess-Manager
```

### 13.2 Service-Befehle (Übersicht)

| Aktion | Linux (systemd) | Windows | Docker |
|---|---|---|---|
| Starten | `sudo systemctl start praxiszeit` | `net start PraxisZeit` | `docker compose up -d` |
| Stoppen | `sudo systemctl stop praxiszeit` | `net stop PraxisZeit` | `docker compose down` |
| Neustart | `sudo systemctl restart praxiszeit` | `net stop PraxisZeit && net start PraxisZeit` | `docker compose restart` |
| Status | `sudo systemctl status praxiszeit` | `sc query PraxisZeit` | `docker compose ps` |
| Logs | `journalctl -u praxiszeit -f` | `type C:\PraxisZeit\logs\praxiszeit.log` | `docker compose logs -f` |
| Autostart | `sudo systemctl enable praxiszeit` | (Default beim Install) | `restart: unless-stopped` |

### 13.3 Wichtige Sicherheitshinweise

- **Niemals** den `SECRET_KEY` oder DB-Passwörter aus `.env`/`praxiszeit.conf` committen
- **Niemals** `ENVIRONMENT=development` in Produktion lassen — Swagger-Docs werden sonst exponiert, Weak-Password-Check wird zur Warnung statt Hard-Failure
- PostgreSQL-Port (5432) **niemals** nach außen öffnen
- Bei externer DB: `sslmode=require` oder `sslmode=verify-full` zwingend
- Admin-Passwort beim Erststart sofort ändern
- Bei Personalwechsel: alte Accounts deaktivieren, nicht löschen (Audit-Trail!)
- Backup-Verschlüsselung bei externer Ablage zusätzlich erwägen (z. B. `gpg --symmetric`)

### 13.4 Support & Ressourcen

| Thema | Quelle |
|---|---|
| Repository | <https://github.com/phash/praxiszeit> |
| Releases / Downloads | <https://github.com/phash/praxiszeit/releases> |
| Admin-Handbuch | `docs/handbuch/HANDBUCH-ADMIN.md` |
| Mitarbeiter-Handbuch | `docs/handbuch/HANDBUCH-MITARBEITER.md` |
| Bug-Reports | <https://github.com/phash/praxiszeit/issues> |
| Architektur-Doku | `docs/ARC42.md`, `docs/BACKEND-ARCHITEKTUR.md` |
| Security-Doku | `docs/SECURITY.md` |

---

*PraxisZeit · Version 1.4.4 · © 2026 · Erstellt am 23. Mai 2026 · Iteration 2*
