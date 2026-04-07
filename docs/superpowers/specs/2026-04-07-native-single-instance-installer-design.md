# PraxisZeit Native Single-Instance Installer — Design & Plan

## Context

PraxisZeit soll als Einzelinstanz auf Kunden-Servern (Windows Server + Linux) installierbar sein. Kunden sind Arztpraxen/MVZs mit 3-100+ Mitarbeitern. Der Kunde oder sein IT-Dienstleister installiert selbst. Docker ist beim Kunden nicht vorausgesetzt. Keine externen Abhängigkeiten nach Installation.

**Gewählter Ansatz:** Embedded Python + Portable PostgreSQL (Ansatz A)
- Python 3.12 Runtime + alle pip-Dependencies gebündelt
- PostgreSQL 16 als portable Binaries
- Frontend-Dateien direkt von FastAPI ausgeliefert (nginx entfällt)
- Process Manager orchestriert PostgreSQL + uvicorn
- Offline-Lizenzschlüssel (Ed25519-signiertes JWT)
- In-App Update-Check gegen zentralen Server

---

## 1. Architektur

### Aktuell (Docker)
```
Browser -> nginx:80/443 -> Backend:8000 -> PostgreSQL:5432
```

### Neu (Native)
```
Browser -> uvicorn:443 (FastAPI: API + Static Files) -> PostgreSQL (portable)
                         ^
                   Process Manager (startet/stoppt beides)
```

### Verzeichnisstruktur
```
/opt/praxiszeit/           (Linux) oder C:\PraxisZeit\ (Windows)
├── bin/
│   ├── python/            # Embedded Python 3.12
│   └── postgresql/        # Portable PostgreSQL 16 Binaries
├── app/
│   ├── backend/           # FastAPI-Quellcode + alembic/
│   └── frontend/          # Gebautes React dist/
├── data/
│   ├── db/                # PostgreSQL-Datenverzeichnis (initdb)
│   └── backups/           # Automatische DB-Backups
├── config/
│   ├── praxiszeit.conf    # Hauptkonfiguration (INI/TOML, ersetzt .env)
│   ├── license.key        # Lizenzschluessel-Datei
│   └── ssl/               # cert.pem + key.pem (optional)
├── logs/
│   └── praxiszeit.log     # Rotiertes Anwendungslog
└── praxiszeit-server      # Process Manager Einstiegspunkt
```

### Wegfallende Komponenten
- **nginx** -> FastAPI `StaticFiles` + `GZipMiddleware` + Security-Header-Middleware
- **Docker** -> Process Manager koordiniert PostgreSQL + uvicorn direkt
- **Prometheus/Grafana** -> Nicht im Basis-Installer (optional nachruestbar)

---

## 2. Process Manager (`praxiszeit-server`)

Zentrales Steuerscript (Python), das als OS-Service laeuft.

### Verantwortlichkeiten
1. **PostgreSQL Lifecycle**: `pg_ctl start/stop`, `pg_isready`-Polling
2. **Erstinitialisierung**: `initdb`, DB + Rollen erstellen, `init-db-user.sql` ausfuehren
3. **Migration**: `alembic upgrade head` bei jedem Start
4. **uvicorn starten**: FastAPI-App mit konfiguriertem Port/SSL
5. **Graceful Shutdown**: SIGTERM/SIGINT -> uvicorn stop -> `pg_ctl stop -m fast`
6. **Health Monitoring**: Watchdog fuer PostgreSQL und uvicorn, Neustart bei Crash
7. **Logging**: Strukturiertes Logging nach `logs/praxiszeit.log` mit Rotation

### Startup-Sequenz
```
1. Config laden (praxiszeit.conf)
2. Lizenz validieren
3. PostgreSQL starten (pg_ctl -D data/db start)
4. Warten auf pg_isready (max 30s, dann Fehler)
5. Falls Erststart: initdb + DB-Setup + init-db-user.sql
6. alembic upgrade head (mit Superuser-Connection)
7. uvicorn starten (mit App-User-Connection)
8. Health-Endpoint bestaetigen
9. Log: "PraxisZeit bereit auf https://localhost:443"
```

### Plattform-Integration
- **Linux**: systemd Unit File -> `ExecStart=/opt/praxiszeit/praxiszeit-server start`
- **Windows**: Windows Service via `nssm` (Non-Sucking Service Manager)

---

## 3. nginx-Ersatz in FastAPI

### Was nginx aktuell macht (aus `frontend/nginx.conf`)
1. Reverse Proxy `/api/` -> `backend:8000`
2. Static File Serving (React `dist/`)
3. SPA Fallback (`try_files $uri /index.html`)
4. Security Headers (HSTS, CSP, X-Frame-Options, etc.)
5. Gzip Compression
6. Cache-Control (immutable fuer Assets, no-cache fuer sw.js)
7. Grafana Proxy (entfaellt)
8. Body Size Limit (2MB)
9. Rate Limiting auf `/api/auth/` (bereits im Backend via slowapi)

### FastAPI-Umsetzung

**Neue Middleware-Datei:** `backend/app/middleware/static_serving.py`

```python
# Security Headers Middleware
class SecurityHeadersMiddleware:
    async def __call__(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # CSP analog zu nginx.conf
        return response
```

**Aenderungen an `backend/app/main.py`:**
```python
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles

# GZip fuer alle Responses
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Security Headers
app.add_middleware(SecurityHeadersMiddleware)

# Static Files (nach allen API-Routen)
if settings.SERVE_FRONTEND:
    app.mount("/assets", StaticFiles(directory=settings.FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """SPA Fallback -- alle nicht-API-Routen liefern index.html"""
        return FileResponse(settings.FRONTEND_DIR / "index.html")
```

**Neue Config-Einstellungen** (`backend/app/config.py`):
```python
SERVE_FRONTEND: bool = False  # True im Native-Modus, False im Docker-Modus
FRONTEND_DIR: Path = Path("../frontend/dist")
```

-> **Docker-Modus bleibt unveraendert**: `SERVE_FRONTEND=False` -> nginx liefert Frontend wie bisher.

---

## 4. Lizenzierung

### Konzept: Ed25519-signiertes JWT

**Schluesselpaar:**
- Privater Schluessel: nur beim Aussteller (Manuel)
- Oeffentlicher Schluessel: in der App eingebettet (`app/core/license.py`)

**Lizenz-Payload (JWT Claims):**
```json
{
  "sub": "praxis-mueller",
  "name": "Praxis Dr. Mueller",
  "max_employees": 20,
  "features": ["base"],
  "iat": 1744070400,
  "exp": 1830384000,
  "v": 1
}
```

**Neues Modul:** `backend/app/core/license.py`
- `validate_license(key_path: Path) -> LicenseInfo`
- Signatur pruefen (Ed25519 Public Key)
- Ablaufdatum pruefen
- `LicenseInfo` Dataclass mit allen Claims

**Enforcement:**
- **Startup**: Lizenz laden und validieren. Ohne gueltige Lizenz: Abbruch mit klarer Fehlermeldung.
- **Periodisch**: Alle 24h re-validieren (fuer Ablauf-Erkennung im Betrieb)
- **Abgelaufen**: Read-Only-Modus (Daten einsehbar + exportierbar, keine neuen Eintraege -> ArbZG-konform)
- **MA-Limit**: Admin-Warnung, neue User koennen nicht erstellt werden

**CLI-Tool fuer Lizenz-Generierung:** `tools/license-generator.py`
- `python license-generator.py generate --customer "Praxis Mueller" --max-employees 20 --expires 2027-12-31 --key private.pem`
- Erzeugt `license.key` Datei

---

## 5. Update-Mechanismus

### Update-Check
```
GET https://updates.praxiszeit.de/v1/check
  ?version=1.2.0
  &license_id=praxis-mueller
  &os=linux

Response:
{
  "latest": "1.3.0",
  "download_url": "https://updates.praxiszeit.de/v1/packages/1.3.0-linux.tar.gz",
  "changelog": "### 1.3.0\n- Neue Funktion X\n- Bugfix Y",
  "size_mb": 12,
  "checksum_sha256": "abc123...",
  "critical": false
}
```

### Neues Modul: `backend/app/core/updater.py`
- Check beim Start + alle 12h (non-blocking Background-Task)
- Ergebnis in `system_settings` speichern (Tabelle existiert bereits)
- Admin-API-Endpoint: `GET /api/admin/updates/check`, `POST /api/admin/updates/download`, `POST /api/admin/updates/apply`

### Update-Ablauf (Admin-UI)
1. Admin sieht Banner "Update 1.3.0 verfuegbar" im Dashboard
2. Klick "Herunterladen" -> Backend laedt Paket + prueft SHA256
3. Klick "Installieren" -> Process Manager:
   - Backup: `pg_dump` + Kopie von `app/`
   - uvicorn stoppen
   - Paket entpacken ueber `app/backend/` und `app/frontend/`
   - `alembic upgrade head`
   - uvicorn starten
   - Health-Check
4. Bei Fehler: automatisches Rollback (Backup zurueckspielen)

### Kein Internet noetig im Betrieb
- Update-Check schlaegt still fehl wenn offline
- App laeuft unbeeinflusst weiter

---

## 6. Plattform-spezifische Installer

### Windows (Inno Setup)

**Paketinhalt:** (~150-200MB)
- Python 3.12 Embeddable (Windows x64)
- PostgreSQL 16 ZIP (Windows x64, von enterprisedb.com)
- pip Dependencies (vorinstalliert in `bin/python/Lib/site-packages/`)
- Frontend dist/
- Backend Quellcode
- nssm.exe (Service Manager)
- OpenSSL (fuer Zertifikat-Generierung)

**Installer-Wizard:**
1. Willkommen / Lizenzvereinbarung
2. Installationsverzeichnis (Standard: `C:\PraxisZeit`)
3. Praxis-Daten: Name, Bundesland (Dropdown), Admin-Email, Admin-Passwort
4. Lizenzschluessel (Datei auswaehlen oder Key einfuegen)
5. Netzwerk: Port (Standard 443), SSL-Zertifikat (Self-Signed generieren oder eigenes)
6. Installation -> Dateien kopieren, Config schreiben, Service registrieren, Firewall-Regel
7. Fertig -> "PraxisZeit im Browser oeffnen"

**Service:** `nssm install PraxisZeit C:\PraxisZeit\bin\python\python.exe C:\PraxisZeit\praxiszeit-server.py`

**Deinstaller:** Service stoppen, Binaries entfernen. Nachfrage: "Datenbank-Dateien beibehalten?"

### Linux (Shell-Script `install.sh`)

**Paketinhalt:** (~120-150MB `.tar.gz`)
- Python 3.12 (Standalone Build, z.B. python-build-standalone von indygreg)
- PostgreSQL 16 Binaries (statisch gelinkt oder aus offiziellen Tarballs)
- pip Dependencies vorinstalliert
- Frontend dist/
- Backend Quellcode

**Installer-Ablauf:**
```bash
$ sudo ./install.sh
PraxisZeit Installer v1.2.0
Praxis-Name: Praxis Dr. Mueller
Bundesland [Bayern]: Bayern
Admin-Email: admin@praxis-mueller.de
Admin-Passwort: ********
Lizenzschluessel-Datei: /tmp/license.key
Port [443]: 443
SSL-Zertifikat generieren? [J/n]: J

-> Installiere nach /opt/praxiszeit/ ...
-> Erstelle System-User praxiszeit ...
-> Schreibe Konfiguration ...
-> Registriere systemd Service ...
-> Starte PraxisZeit ...
-> Erstelle Backup-Cronjob (taeglich 02:00) ...

PraxisZeit laeuft auf https://192.168.1.50:443
```

**systemd Unit:**
```ini
[Unit]
Description=PraxisZeit Zeiterfassung
After=network.target

[Service]
Type=simple
User=praxiszeit
ExecStart=/opt/praxiszeit/bin/python/bin/python3 /opt/praxiszeit/praxiszeit-server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## 7. Backup-System

### Automatisch (bereits existierend, anpassen)
- Basis: `scripts/backup-db.sh` (existiert bereits)
- Anpassung: Pfade fuer native Installation
- Linux: Cron-Job bei Installation erstellt (taeglich 02:00)
- Windows: Windows Task Scheduler
- Retention: 31 Tage (konfigurierbar)
- Speicherort: `data/backups/`

### Vor Updates
- Process Manager erstellt automatisch Backup vor jedem Update
- DB-Dump + Dateisystem-Snapshot von `app/`

---

## 8. Konfigurationsdatei

`config/praxiszeit.conf` (TOML-Format, ersetzt .env im Native-Modus):

```toml
[server]
port = 443
ssl_cert = "config/ssl/cert.pem"
ssl_key = "config/ssl/key.pem"

[database]
data_dir = "data/db"
superuser = "praxiszeit"
app_user = "praxiszeit_app"

[practice]
name = "Praxis Dr. Mueller"
address = "Musterstrasse 1, 80000 Muenchen"
holiday_state = "Bayern"

[admin]
username = "admin"
email = "admin@praxis-mueller.de"

[security]
secret_key = "auto-generated-on-install"
login_rate_limit = "5/minute"
cookie_secure = true

[license]
key_file = "config/license.key"

[updates]
check_enabled = true
server_url = "https://updates.praxiszeit.de"
check_interval_hours = 12

[backup]
enabled = true
schedule = "02:00"
retention_days = 31
```

---

## 9. Kompatibilitaet mit Docker-Modus

**Wichtig:** Der Docker-Deployment-Modus (docker-compose) bleibt voll funktionsfaehig.

Die Aenderungen sind additiv:
- `SERVE_FRONTEND` Flag (default `False`) -> Docker nutzt weiter nginx
- Neue Module (`license.py`, `updater.py`) sind optional (kein Lizenz-Check im Docker-Modus, steuerbar via Config)
- Process Manager ist ein separates Script, das Docker nicht beeinflusst
- `praxiszeit.conf` ist eine Alternative zu `.env`, nicht ein Ersatz

---

## 10. Kritische Dateien fuer die Implementierung

| Datei | Aenderung |
|-------|----------|
| `backend/app/main.py` | StaticFiles Mount, SPA Fallback, GZipMiddleware |
| `backend/app/config.py` | Neue Settings: SERVE_FRONTEND, FRONTEND_DIR, LICENSE_KEY_PATH, UPDATE_SERVER_URL |
| `backend/app/middleware/static_serving.py` | **Neu**: Security-Header-Middleware |
| `backend/app/core/license.py` | **Neu**: Lizenz-Validierung (Ed25519) |
| `backend/app/core/updater.py` | **Neu**: Update-Check + Download + Apply |
| `backend/app/routers/admin.py` | Neue Endpoints: /updates/check, /updates/download, /updates/apply |
| `frontend/src/pages/AdminDashboard.tsx` | Update-Benachrichtigung + Lizenz-Info |
| `praxiszeit-server.py` | **Neu**: Process Manager (PostgreSQL + uvicorn) |
| `installer/windows/praxiszeit.iss` | **Neu**: Inno Setup Script |
| `installer/linux/install.sh` | **Neu**: Linux Installer |
| `tools/license-generator.py` | **Neu**: Lizenz-Generierungs-CLI |
| `tools/build-release.sh` | **Neu**: Release-Paket bauen (Windows + Linux) |

---

## 11. Verifikation / Testplan

1. **Unit Tests**: License-Modul, Updater-Modul, Security-Header-Middleware
2. **Integrationstests**: Process Manager Startup/Shutdown-Sequenz
3. **E2E auf Linux**: `install.sh` auf frischem Ubuntu 24.04 -> kompletter Durchlauf
4. **E2E auf Windows**: Inno Setup Installer auf Windows Server 2022 -> kompletter Durchlauf
5. **Update-Test**: Version 1.0 installieren -> Update auf 1.1 einspielen -> Daten pruefen
6. **Lizenz-Tests**: Gueltige Lizenz, abgelaufene Lizenz (Read-Only), MA-Limit, keine Lizenz
7. **Rollback-Test**: Update fehlschlagen lassen -> automatisches Rollback pruefen
8. **Bestehende Tests**: Alle 343 Backend-Unit-Tests + 114 E2E-Tests + 13 RLS-Tests muessen weiter gruen sein

---

## 12. Implementierungsreihenfolge

### Phase 1: Backend-Anpassungen (Basis)
1. `SERVE_FRONTEND` Flag + StaticFiles + SPA Fallback + Security-Header-Middleware
2. Config-Erweiterung (`config.py`) fuer native Einstellungen
3. TOML Config-Loader als Alternative zu .env

### Phase 2: Lizenzierung
4. `core/license.py` -- Ed25519 Validierung
5. `tools/license-generator.py` -- CLI zum Ausstellen
6. Lizenz-Enforcement in Startup + periodisch
7. Read-Only-Modus bei abgelaufener Lizenz

### Phase 3: Process Manager
8. `praxiszeit-server.py` -- PostgreSQL + uvicorn Orchestrierung
9. Erstinitialisierung (initdb, DB-Setup, Migrations)
10. Graceful Shutdown + Watchdog
11. Logging mit Rotation

### Phase 4: Update-System
12. `core/updater.py` -- Check, Download, Apply
13. Admin-API-Endpoints fuer Updates
14. Frontend: Update-Banner im Admin-Dashboard
15. Rollback-Mechanismus

### Phase 5: Installer
16. Linux `install.sh` + systemd Unit + Backup-Cron
17. Windows Inno Setup Script + nssm Service
18. `tools/build-release.sh` -- Release-Pakete schnueren

### Phase 6: Test & Dokumentation
19. Tests fuer alle neuen Module
20. E2E auf frischem Linux + Windows
21. Installations-Handbuch fuer Kunden
