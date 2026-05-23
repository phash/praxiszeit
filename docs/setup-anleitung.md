# Setup-Anleitung PraxisZeit

**Version 1.4.3** · Stand: 23. Mai 2026
Für Linux und Windows · Native Installation und Docker-Deployment

---

## Inhaltsverzeichnis

1. **Einführung** — Was ist PraxisZeit, welche Variante ist die richtige?
2. **Voraussetzungen** — Hardware, Netzwerk, Berechtigungen
3. **Variante A: Native Installation (Linux)**
4. **Variante B: Native Installation (Windows)**
5. **Variante C: Docker-Deployment (Linux)**
6. **Konfiguration** — `praxiszeit.conf` und `.env`
7. **HTTPS / SSL aktivieren**
8. **Backup & Wiederherstellung** (inkl. § 16 ArbZG)
9. **Updates einspielen**
10. **Erster Login & Onboarding**
11. **Troubleshooting**
12. **Anhang** — Verzeichnisstruktur, Service-Befehle, Support

---

## 1. Einführung

PraxisZeit ist eine **Arbeitszeiterfassung speziell für Arzt- und Therapie-Praxen** mit voller Konformität zum deutschen Arbeitszeitgesetz (ArbZG) und zur DSGVO.

### Welche Installations-Variante wähle ich?

| Kriterium | Native (A/B) | Docker (C) |
|---|---|---|
| Praxis-Server ohne IT-Erfahrung | ✅ empfohlen | — |
| Vorhandener Linux-Server mit Docker-Wissen | — | ✅ empfohlen |
| Updates per Klick / Wizard | ✅ Avalonia-Setup | — |
| Mehrere Instanzen parallel | — | ✅ |
| Windows als Server | ✅ einzige Option | — |
| macOS als Server | ✅ Native | — |
| Cloud-Hosting | — | ✅ |

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
| 80 (HTTP) | Browser-Zugriff im LAN | Firewall öffnen |
| 443 (HTTPS) | Verschlüsselter Zugriff | Firewall öffnen |
| 5432 | PostgreSQL (intern) | NICHT nach außen öffnen |

---

## 3. Variante A: Native Installation (Linux)

### 3.1 Paket herunterladen

```bash
# Aktuelle Version 1.4.3 herunterladen
wget https://updates.praxiszeit.de/praxiszeit-1.4.3-linux-x64.tar.gz

# Prüfsumme kontrollieren (empfohlen)
wget https://updates.praxiszeit.de/praxiszeit-1.4.3-SHA256SUMS.txt
sha256sum -c praxiszeit-1.4.3-SHA256SUMS.txt --ignore-missing
# Erwartete Ausgabe: praxiszeit-1.4.3-linux-x64.tar.gz: OK
```

### 3.2 Entpacken und installieren

```bash
# Entpacken
tar xzf praxiszeit-1.4.3-linux-x64.tar.gz
cd praxiszeit

# Installer als root starten
sudo ./install.sh
```

Der Installer fragt interaktiv ab:

| Eingabe | Beispiel | Hinweis |
|---|---|---|
| Praxis-Name | `Praxis Dr. Müller` | Erscheint im Login und auf Exporten |
| Admin-Benutzername | `admin` | Pflicht, eindeutig |
| Admin-Email | `admin@praxis.local` | Pflicht, eindeutig |
| Admin-Passwort | `********` | Min. 12 Zeichen, Komplexität geprüft |
| HTTP-Port | `80` | Frei wählbar (z. B. `8080` falls 80 belegt) |
| Bundesland | `Bayern` | Steuert die Feiertags-Erkennung |

Der Installer:
- Erzeugt den Systembenutzer `praxiszeit`
- Initialisiert PostgreSQL unter `/opt/praxiszeit/data/db`
- Spielt alle DB-Migrationen ein
- Registriert einen `systemd`-Service

### 3.3 Service starten

```bash
sudo systemctl start praxiszeit            # Starten
sudo systemctl enable praxiszeit           # Autostart aktivieren
sudo systemctl status praxiszeit           # Status prüfen
journalctl -u praxiszeit -f                # Live-Log anschauen
```

**Erwartete Statusmeldung:**
```
● praxiszeit.service - PraxisZeit Time Tracking
   Active: active (running) since ...
   Main PID: 12345 (python)
```

### 3.4 Im Browser öffnen

```
http://<server-ip>      (LAN)
http://localhost        (lokal)
```

Server-IP herausfinden:
```bash
hostname -I
```

→ Login mit den im Installer gesetzten Admin-Daten.

---

## 4. Variante B: Native Installation (Windows)

> Ab Version 1.4.0 steht alternativ ein **grafischer Setup-Wizard** (Avalonia) zur Verfügung. Die folgende Anleitung beschreibt den klassischen Batch-Installer; der GUI-Wizard fragt dieselben Daten in Dialog-Schritten ab.

### 4.1 Paket herunterladen und entpacken

1. `praxiszeit-1.4.3-windows-x64.zip` von <https://updates.praxiszeit.de> herunterladen
2. **Rechtsklick** auf die ZIP → **Eigenschaften** → Häkchen bei **„Zulassen"** setzen (entfernt die SmartScreen-Blockade)
3. Entpacken nach `C:\PraxisZeit\` (NICHT in `C:\Program Files\`, da Schreibrechte benötigt werden)

### 4.2 PostgreSQL und Python einrichten

> **Wichtig:** Eingabeaufforderung als **Administrator** öffnen (Rechtsklick → „Als Administrator ausführen").

```cmd
cd C:\PraxisZeit
setup.bat
```

Das Script:
- Sucht nach vorhandener PostgreSQL-Installation (Major ≥ 16) und nutzt sie ggf. wieder (Junction)
- Installiert sonst PostgreSQL 16.8 still aus dem mitgelieferten EDB-Installer
- Bootstrappt `pip` und installiert Python-Abhängigkeiten (benötigt einmalig Internet)
- Generiert einen kryptographisch sicheren `SECRET_KEY` in `config\.secret-key`

**Bei Fehlermeldung „Setup kann nicht starten":**
- Sicherstellen, dass das Eingabeaufforderungs-Fenster wirklich als Administrator läuft
- Antivirus temporär deaktivieren — manche AV-Lösungen blocken `nssm.exe`

### 4.3 Konfiguration anlegen

```cmd
copy config\praxiszeit.conf.example config\praxiszeit.conf
notepad config\praxiszeit.conf
```

> **⚠️ Niemals mit Notepad speichern, wenn UTF-8-BOM aktiv ist** — das bricht das TOML-Parsing. Notepad++ oder VS Code mit Kodierung **„UTF-8 ohne BOM"** verwenden.

Mindestens folgende Werte anpassen:

```toml
[practice]
name = "Praxis Dr. Müller"
holiday_state = "Bayern"

[admin]
username = "admin"
email = "admin@praxis.local"
password = "REDACTED-PW"   # nur Erststart, danach in DB gehasht

[server]
port = 80
```

### 4.4 Dienst registrieren und starten

```cmd
install-service.bat
net start PraxisZeit
```

Status prüfen:
```cmd
sc query PraxisZeit
type C:\PraxisZeit\logs\praxiszeit.log
```

Browser öffnen: `http://localhost` oder `http://<server-ip>`

### 4.5 Windows-Spezifika beachten

- **Firewall:** `install-service.bat` öffnet automatisch Port 80. Bei abweichendem Port manuell freigeben: `netsh advfirewall firewall add rule name="PraxisZeit" dir=in action=allow protocol=TCP localport=8080`
- **Automatischer Start:** Der Dienst startet beim Booten automatisch (`Automatic`)
- **Updates:** Über den integrierten Update-Wizard (Browser → Admin → Updates) oder durch erneutes Ausführen von `setup.bat` mit neuem Paket
- **Deinstallation:** `uninstall-service.bat` — die Datenbank bleibt erhalten

---

## 5. Variante C: Docker-Deployment (Linux Mint 22 / Ubuntu 24.04)

### 5.1 Docker installieren

```bash
# Eventuell vorhandene alte Versionen entfernen
sudo apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null

# Voraussetzungen
sudo apt update
sudo apt install -y ca-certificates curl gnupg

# Docker-GPG-Schlüssel hinterlegen
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Repository hinzufügen
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu noble stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker Engine installieren
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

# Benutzer zur docker-Gruppe hinzufügen (kein sudo mehr nötig)
sudo usermod -aG docker $USER

# WICHTIG: Ab- und wieder anmelden, damit die Gruppen-Mitgliedschaft greift
docker --version
docker compose version
```

### 5.2 Repository klonen

```bash
cd ~
git clone https://github.com/phash/praxiszeit.git
cd praxiszeit
```

### 5.3 `.env` anlegen

> **⚠️ Sicherheit:** Vor dem Erststart **alle** Passwörter und den `SECRET_KEY` durch eigene, zufällig generierte Werte ersetzen.

```bash
# Sichere Zufallswerte generieren
POSTGRES_PW=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)
SECRET=$(python3 -c "import secrets; print(secrets.token_hex(64))")

cat > .env << EOF
# ====== Datenbank ======
POSTGRES_USER=praxiszeit
POSTGRES_PASSWORD=$POSTGRES_PW
POSTGRES_DB=praxiszeit

# ====== App-User für RLS (Phase-3-Multi-Tenant) ======
APP_DB_USER=praxiszeit_app
APP_DB_PASSWORD=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)

# ====== Backend / Security ======
SECRET_KEY=$SECRET
DATABASE_URL=postgresql://praxiszeit:$POSTGRES_PW@db:5432/praxiszeit
ENVIRONMENT=production
DEPLOYMENT_MODE=onprem
ACCESS_TOKEN_EXPIRE_MINUTES=480
REFRESH_TOKEN_EXPIRE_DAYS=30
CORS_ORIGINS=https://praxis.local,http://localhost

# ====== Admin (nur Erststart) ======
ADMIN_EMAIL=admin@praxis.local
ADMIN_PASSWORD=Bitte-Aendern-2026!
ADMIN_FIRST_NAME=Dr.
ADMIN_LAST_NAME=Müller
EOF

chmod 600 .env   # nur Owner darf lesen
```

> **Warum `ENVIRONMENT=production`?** Im Produktiv-Modus werden die Swagger-/ReDoc-Endpunkte deaktiviert und sicherheitsrelevante Defaults aktiviert.

### 5.4 Starten

```bash
docker compose up -d
```

Erststart dauert 3–5 Minuten (Image-Build + DB-Init). Fortschritt verfolgen:
```bash
docker compose logs -f
# Strg+C beendet nur die Log-Anzeige, nicht den Container
```

Gesundheits-Check:
```bash
docker compose ps             # alle 3 Container sollten "Up" sein
curl http://localhost/api/health
# {"status":"healthy","database":"connected"}
```

### 5.5 Im LAN erreichbar machen

```bash
# Firewall (falls ufw aktiv)
sudo ufw allow 80/tcp

# Server-IP herausfinden
hostname -I
```

Andere Geräte im Netz öffnen `http://<server-ip>` im Browser.

---

## 6. Konfiguration

### 6.1 Native: `config/praxiszeit.conf`

```toml
[server]
port = 443
ssl_cert = "config/ssl/cert.pem"     # leer = kein SSL
ssl_key  = "config/ssl/key.pem"

[practice]
name = "Praxis Dr. Müller"
address = "Musterstr. 1, 80000 München"
holiday_state = "Bayern"             # für korrekte Feiertage

[security]
login_rate_limit = "5/minute"
cookie_secure = true                 # MUSS false sein, wenn ohne SSL!

[license]
key_file = "config/license.key"      # optional, Ed25519-signiert

[updates]
check_enabled = true
server_url = "https://updates.praxiszeit.de"

[backup]
enabled = true
schedule = "02:00"
retention_days = 730                 # § 16 ArbZG: min. 2 Jahre!
```

### 6.2 Docker: `.env`-Variablen

| Variable | Pflicht | Default | Erklärung |
|---|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | ✅ | — | Superuser, nur für Migrationen |
| `APP_DB_USER` / `APP_DB_PASSWORD` | ✅ | — | App-Verbindung mit RLS-Enforcement |
| `SECRET_KEY` | ✅ | — | min. 64 Hex-Zeichen, niemals defaulten |
| `DATABASE_URL` | ✅ | — | inkl. `sslmode=require` bei externer DB |
| `ENVIRONMENT` | ✅ | `development` | auf `production` setzen vor Exposition |
| `DEPLOYMENT_MODE` | — | `onprem` | `saas` nur für gehostete Mandanten-Variante |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | — | 480 (8 h) | Session-Lebensdauer |
| `CORS_ORIGINS` | ✅ in Prod | — | Komma-Liste erlaubter Origins |

---

## 7. HTTPS / SSL aktivieren

### 7.1 Variante A/B (Native)

```bash
# Selbstsigniertes Zertifikat (10 Jahre)
openssl req -x509 -newkey ed25519 \
  -keyout /opt/praxiszeit/config/ssl/key.pem \
  -out    /opt/praxiszeit/config/ssl/cert.pem \
  -days 3650 -nodes \
  -subj "/CN=PraxisZeit"

# In praxiszeit.conf:
# [server]
# port = 443
# ssl_cert = "config/ssl/cert.pem"
# ssl_key  = "config/ssl/key.pem"
# [security]
# cookie_secure = true

sudo systemctl restart praxiszeit
```

> Windows: identisch — `openssl.exe` aus dem PostgreSQL-Bundle (`C:\PraxisZeit\bin\postgresql\bin\openssl.exe`) verwenden.

### 7.2 Variante C (Docker)

```bash
cd ~/praxiszeit
chmod +x ssl/generate-cert.sh
./ssl/generate-cert.sh                            # erkennt Server-IP automatisch

docker compose down
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d

sudo ufw allow 443/tcp
```

Browser zeigt **einmalig** eine Sicherheitswarnung (selbstsigniert) — bestätigen, danach läuft die Verbindung verschlüsselt.

**Für „echte" Zertifikate** (z. B. Let's Encrypt mit Caddy als Reverse-Proxy): siehe `docs/INFRASTRUCTURE.md` im Repo.

---

## 8. Backup & Wiederherstellung

### 8.1 § 16 ArbZG — Pflichten kurzgefasst

Arbeitgeber müssen Arbeitszeiten **mindestens 2 Jahre** revisionssicher aufbewahren. Verstöße: Bußgeld bis 30.000 €. Diese Pflicht liegt beim Arbeitgeber — PraxisZeit liefert die Werkzeuge, nicht die Aufbewahrung selbst.

### 8.2 Automatische Backups (Native)

Sind im Installer ab Werk aktiviert (täglich 02:00, 31 Tage Retention). Für die ArbZG-Konformität die Retention erhöhen:

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

### 8.3 Backups (Docker)

```bash
# Manuell
docker compose exec db pg_dump -U praxiszeit praxiszeit \
  | gzip > ~/backups/praxiszeit_$(date +%Y%m%d).sql.gz

# Täglich per Cron (2:00 Uhr, 30-Tage-Rotation)
crontab -e
# Zeile anhängen:
0 2 * * * cd ~/praxiszeit && docker compose exec -T db pg_dump -U praxiszeit praxiszeit | gzip > ~/backups/praxiszeit_$(date +\%Y\%m\%d).sql.gz && find ~/backups -name "praxiszeit_*.sql.gz" -mtime +30 -delete

# Jahresarchiv (zum Jahresende)
YEAR=$(date +%Y)
docker compose exec -T db pg_dump -U praxiszeit praxiszeit \
  | gzip > ~/praxiszeit-archiv/praxiszeit_${YEAR}.sql.gz
```

### 8.4 Wiederherstellung

**Native (Windows):** `restore-backup.bat` aus dem Installer-Verzeichnis ausführen.

**Native (Linux/macOS):**
```bash
sudo systemctl stop praxiszeit
sudo -u postgres psql -d praxiszeit < /opt/praxiszeit/data/backups/<dump>.sql
sudo systemctl start praxiszeit
```

**Docker:**
```bash
docker compose exec -T db psql -U praxiszeit praxiszeit < backup_20260214.sql
```

### 8.5 Compliance-Checkliste

- [ ] Automatisches tägliches Backup eingerichtet
- [ ] Retention ≥ 2 Jahre (730 Tage)
- [ ] Backup-Ablage **außerhalb** des Servers (NAS, externe HDD, Cloud)
- [ ] Mindestens 1× pro Quartal Wiederherstellung getestet
- [ ] Excel-Exporte werden ebenfalls 2 Jahre archiviert
- [ ] Verantwortliche Person für Backup-Monitoring benannt

---

## 9. Updates einspielen

### 9.1 Native (alle Plattformen)

**Variante 1 — Update-Wizard im Browser** (empfohlen):
1. Im Browser einloggen als Admin
2. Menü → **Einstellungen → Updates**
3. „Nach Updates suchen" → falls verfügbar: „Update installieren"
4. Dienst startet automatisch neu, Browser-Hard-Refresh nicht vergessen (`Strg + F5`)

**Variante 2 — Neues Paket manuell:**
```bash
# Linux
sudo systemctl stop praxiszeit
tar xzf praxiszeit-1.4.4-linux-x64.tar.gz -C /opt/praxiszeit --strip-components=1
sudo systemctl start praxiszeit

# Windows
net stop PraxisZeit
# ZIP entpacken (überschreibt nur app/, bin/, scripts/ — config + data bleiben)
net start PraxisZeit
```

### 9.2 Docker

```bash
cd ~/praxiszeit
git pull
docker compose down
# Ohne SSL:
docker compose up -d --build
# Mit SSL:
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build
```

DB-Migrationen laufen automatisch beim Backend-Start.

### 9.3 Nach jedem Update

- **Browser:** Hard-Refresh (`Strg + F5`) oder Service-Worker im DevTools deregistrieren — sonst bleibt der alte JS-Code im Cache
- **Version verifizieren:** Im Footer der Anwendung muss `v1.4.3` (bzw. die neue Version) erscheinen
- **Backend-Health:** `curl http://localhost/api/health` → `{"status":"healthy"}`

---

## 10. Erster Login & Onboarding

1. `http://<server-ip>` (bzw. `https://`) im Browser öffnen
2. Login mit Admin-Daten aus Installer / `.env`
3. **Pflicht:** Admin-Passwort sofort unter `Profil → Passwort ändern` neu setzen
4. Praxis-Daten vervollständigen: `Einstellungen → Praxis`
5. Erste Mitarbeitenden anlegen: `Mitarbeiter → Neu`
6. Wöchentliche Soll-Stunden, Urlaubsanspruch und Vertragsbeginn pro Person eintragen
7. Test-Stempelung über `Stempeluhr` → kontrollieren, dass Eintrag in „Heute" erscheint

**Onboarding-Tipp:** Mitarbeitende per Magic-Link einladen (`Mitarbeiter → Einladen`) — sie setzen Passwort selbst, der Admin lernt das Mitarbeiter-Passwort nie.

---

## 11. Troubleshooting

| Problem | Diagnose | Lösung |
|---|---|---|
| Browser zeigt „Seite nicht erreichbar" | `curl http://localhost/api/health` schlägt fehl | Service-Status prüfen, Logs lesen, ggf. Firewall öffnen |
| `setup.bat` bricht mit Syntaxfehler | Windows | Eingabeaufforderung als Administrator starten, Passwort ohne `!` und `&` |
| Login funktioniert, aber Stempeluhr lädt nicht | Browser-Konsole zeigt 405 | Hard-Refresh, ggf. Service-Worker deregistrieren |
| „Network Error" trotz SSL-Setup | Docker | `-f docker-compose.ssl.yml` beim `up -d` vergessen |
| Backend-Container startet nicht | `docker compose logs backend` zeigt `APP_DB_PASSWORD missing` | `.env` fehlt Multi-Tenant-Vars, `.env.example` als Referenz |
| Migration schlägt fehl | `journalctl -u praxiszeit -n 100` | Datenbank-Verbindung prüfen, ggf. Backup zurückspielen |
| Cookie wird nicht gesetzt (kein Login möglich) | Ohne SSL | `cookie_secure = false` in `praxiszeit.conf`, oder SSL aktivieren |
| Frontend zeigt alte Version nach Update | Browser-Cache | Hard-Refresh `Strg + F5`, Cache leeren |
| `praxiszeit.conf` wird nicht gelesen | Windows | Notepad hat UTF-8-BOM geschrieben — mit VS Code/Notepad++ als „UTF-8 ohne BOM" speichern |
| `setup.bat` will PG neu installieren obwohl schon vorhanden | Windows | Existierende PG-Installation muss Major-Version ≥ 16 sein |

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

## 12. Anhang

### 12.1 Verzeichnisstruktur (Native)

```
/opt/praxiszeit/                  (Linux)
C:\PraxisZeit\                    (Windows)
/usr/local/praxiszeit/            (macOS)
│
├── bin/
│   ├── python/                   Python 3.13 (gebündelt)
│   └── postgresql/               PostgreSQL 16 (gebündelt)
├── app/
│   ├── backend/                  FastAPI + Alembic
│   └── frontend/                 React (kompiliert)
├── data/
│   ├── db/                       PostgreSQL-Daten
│   └── backups/                  tägliche Backups
├── config/
│   ├── praxiszeit.conf           Hauptkonfiguration
│   ├── .secret-key               (auto-generiert, NICHT löschen!)
│   ├── license.key               (optional)
│   └── ssl/                      SSL-Zertifikate
├── logs/
│   └── praxiszeit.log            rotiert, max. 50 MB
└── praxiszeit-server.py          Prozess-Manager
```

### 12.2 Service-Befehle (Übersicht)

| Aktion | Linux (systemd) | Windows | Docker |
|---|---|---|---|
| Starten | `sudo systemctl start praxiszeit` | `net start PraxisZeit` | `docker compose up -d` |
| Stoppen | `sudo systemctl stop praxiszeit` | `net stop PraxisZeit` | `docker compose down` |
| Neustart | `sudo systemctl restart praxiszeit` | `net stop PraxisZeit && net start PraxisZeit` | `docker compose restart` |
| Status | `sudo systemctl status praxiszeit` | `sc query PraxisZeit` | `docker compose ps` |
| Logs | `journalctl -u praxiszeit -f` | `type C:\PraxisZeit\logs\praxiszeit.log` | `docker compose logs -f` |
| Autostart | `sudo systemctl enable praxiszeit` | (Default beim Install) | `restart: unless-stopped` |

### 12.3 Wichtige Sicherheitshinweise

- **Niemals** den `SECRET_KEY` oder DB-Passwörter aus `.env`/`praxiszeit.conf` committen
- **Niemals** `ENVIRONMENT=development` in Produktion lassen — Swagger-Docs werden sonst exponiert
- PostgreSQL-Port (5432) **niemals** nach außen öffnen
- Bei externer DB: `sslmode=require` oder `sslmode=verify-full` zwingend
- Admin-Passwort beim Erststart sofort ändern
- Bei Personalwechsel: alte Accounts deaktivieren, nicht löschen (Audit-Trail!)

### 12.4 Support & Ressourcen

| Thema | Quelle |
|---|---|
| Repository | <https://github.com/phash/praxiszeit> |
| Updates | <https://updates.praxiszeit.de> |
| Admin-Handbuch | `docs/handbuch/HANDBUCH-ADMIN.md` |
| Mitarbeiter-Handbuch | `docs/handbuch/HANDBUCH-MITARBEITER.md` |
| Bug-Reports | GitHub Issues |
| Architektur-Doku | `docs/ARC42.md`, `docs/BACKEND-ARCHITEKTUR.md` |
| Security-Doku | `docs/SECURITY.md` |

---

*PraxisZeit · Version 1.4.3 · © 2026 · Erstellt am 23. Mai 2026*
