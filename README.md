# PraxisZeit - Zeiterfassungssystem

Webbasiertes Zeiterfassungssystem für eine Arztpraxis in Bayern.
Installierbar als **Progressive Web App (PWA)** auf Smartphone und Desktop.

## Features

### Für Mitarbeiter
- ✅ **Stempeluhr** - Ein-/Ausstempeln direkt auf dem Dashboard
- ✅ **Zeiterfassung** (von–bis mit Pausen)
- ✅ **Dashboard** mit Soll/Ist-Vergleich und Überstundenkonto
- ✅ **Urlaubsverwaltung** (stundenbasiert mit Restanzeige)
- ✅ **Abwesenheiten** (Urlaub, Krankheit, Fortbildung, Überstundenausgleich, Sonstiges)
- ✅ **Abwesenheiten mit Zeiten** (Start-/Endzeit oder "ganzer Tag")
- ✅ **Zeitraum-Erfassung** (mehrere Tage auf einmal)
- ✅ **Profilseite** (Passwort ändern, persönliche Daten)
- ✅ **Änderungsanträge** für vergangene Tage (Arbeitszeit + Abwesenheiten)

### Für Admins
- ✅ **Benutzerverwaltung** mit Rollenverwaltung
- ✅ **Arbeitszeiten-Historie** (Stundenänderungen nachverfolgen)
- ✅ **Individuelle Tagesplanung** (Stunden je Wochentag konfigurierbar)
- ✅ **Urlaubsübersicht** (Budget, Verbrauch, Resturlaub pro MA)
- ✅ **Kalenderfarben** für Abwesenheitskalender
- ✅ **Admin-Dashboard** mit Team-Übersicht
- ✅ **Berichte & Export**:
  - Monatsreport (detailliert mit täglichen Einträgen)
  - Jahresreport Classic (kompakte 12-Monats-Übersicht)
  - Jahresreport Detailliert (365 Tage pro MA)
- ✅ **Abwesenheitskalender** für das ganze Team
- ✅ **Änderungsanträge** genehmigen/ablehnen
- ✅ **Fehler-Monitoring** (Backend-Fehler mit Status und GitHub-Integration)
- ✅ **Änderungsprotokoll** (Audit-Log aller Systemaktionen)
- ✅ **ArbZG-Compliance-Reports**: Ruhezeitverstöße (§5), Sonntagsarbeit (§11), Nachtarbeit (§6), Ersatzruhetag-Tracking (§11)

### ArbZG-Compliance (§3–§18)
- ⚖️ **§3**: 8h-Warnung + 10h-Hard-Stop an allen Eingabepfaden (inkl. Admin-Direkteintrag, Änderungsanträge)
- ⚖️ **§4**: Pflichtpause-Prüfung (>6h→30min, >9h→45min) + Mindestdauer-Warnung (<15min, §4 Satz 2)
- ⚖️ **§5**: 11h-Mindestruhezeit — Echtzeit-Warnung beim Einstempeln + Admin-Report
- ⚖️ **§6**: Nachtarbeit-Erkennung (23–6 Uhr), Badge im Frontend, Admin-Report mit Nachtarbeitnehmer-Schwellwert (≥48 Tage/Jahr)
- ⚖️ **§9/10**: Sonn-/Feiertagserkennung, Warnungen, optionales Ausnahmegrund-Feld (`sunday_exception_reason`)
- ⚖️ **§11**: 15-freie-Sonntage-Report + Ersatzruhetag-Tracking (2/8 Wochen)
- ⚖️ **§14**: 48h-Wochenarbeitszeit-Warnung
- ⚖️ **§16**: Excel-Export, 2-Jahres-Retention-Dokumentation, Link zum Gesetzestext
- ⚖️ **§18**: `exempt_from_arbzg`-Flag für leitende Angestellte (Chefärzte, Praxisinhaber)

### Weitere Features
- 📱 **PWA** - Installierbar als App auf Smartphone und Desktop
- 🗓️ **Bayerischer Feiertagskalender** (automatisch berücksichtigt)
- 📅 **Wochenenden** automatisch ausschließen bei Zeiträumen
- 📊 **Historische Stundenänderungen** werden korrekt berechnet
- 🎨 **Responsive Design** – Hamburger-Menü, Card-Layouts auf Mobile für alle Tabellen
- ♿ **Barrierefreiheit (A11y)** – ARIA-Rollen, FocusTrap, Keyboard-Navigation, screenreader-optimiert
- 🔔 **Toast-Notifications** – Styled Benachrichtigungen statt browser-native alert/confirm
- ❤️ **Health Check** (`/api/health`) mit DB-Connectivity-Test

## Technologie-Stack

- **Backend:** Python 3.12 + FastAPI + SQLAlchemy + PostgreSQL
- **Frontend:** React + TypeScript + Vite + Tailwind CSS
- **PWA:** vite-plugin-pwa + Workbox (Service Worker)
- **Deployment:** Docker Compose

## Installation

### Voraussetzungen

- Docker & Docker Compose
- (optional) Node.js 20+ für lokale Frontend-Entwicklung
- (optional) Python 3.12+ für lokale Backend-Entwicklung

### Setup

1. **Repository klonen:**
```bash
git clone https://github.com/phash/praxiszeit.git
cd praxiszeit
```

2. **Environment-Variablen konfigurieren:**
```bash
cp .env.example .env
```

Bearbeite `.env` und setze:
- `POSTGRES_PASSWORD` - Datenbank-Passwort
- `SECRET_KEY` - JWT Secret (generiere mit `openssl rand -hex 32`)
- `ADMIN_EMAIL` - Admin E-Mail (z.B. admin@praxis.de)
- `ADMIN_PASSWORD` - Admin Passwort

3. **Docker Container starten:**
```bash
docker-compose up -d
```

Die Datenbank wird automatisch initialisiert und Migrationen ausgeführt.

4. **Anwendung öffnen:**
```
Frontend: http://localhost
Backend API: http://localhost:8000
API Docs: http://localhost:8000/docs
```

### PWA-Installation

PraxisZeit kann als App auf dem Smartphone oder Desktop installiert werden:

- **Chrome/Edge (Desktop):** Adressleiste → "App installieren"
- **Chrome (Android):** Menü → "App installieren" oder "Zum Startbildschirm"
- **Safari (iOS):** Teilen → "Zum Home-Bildschirm"
- **Im WLAN:** `http://<SERVER-IP>` im Browser öffnen

### Initiales Admin-Login

Die Zugangsdaten für den Admin-Account sind in der `.env`-Datei definiert:
- **Email:** Siehe `ADMIN_EMAIL`
- **Password:** Siehe `ADMIN_PASSWORD`

### Test-Daten generieren (optional)

Um das System mit realistischen Test-Daten für 2026 zu befüllen:

```bash
docker-compose exec backend python create_test_data.py
```

Dies erstellt:
- 4 Mitarbeiterinnen (2 Vollzeit, 2 Teilzeit)
- Vollständige Zeiteinträge für 2026
- Realistische Abwesenheiten (Urlaub, Krankheit, Fortbildung)
- Arbeitszeiten-Änderung (Sophie Schmidt: 30h → 20h ab März)

## Stempeluhr

Die Stempeluhr erscheint oben auf dem Dashboard und ermöglicht schnelles Ein-/Ausstempeln:

- **Einstempeln:** Grüner Button → erstellt Zeiteintrag mit Startzeit = jetzt
- **Ausstempeln:** Roter Button → fragt Pausenminuten ab, setzt Endzeit = jetzt
- **Live-Anzeige:** Zeigt laufende Arbeitszeit seit Einstempeln
- **Vergessenes Ausstempeln:** Wird beim nächsten Einstempeln automatisch um 23:59 geschlossen
- **Mehrere Einträge/Tag:** Nach Ausstempeln kann erneut eingestempelt werden

## Datenbank

### Struktur

- **users** - Benutzer mit Rollen, Wochenstunden, Urlaubsanspruch, Kalenderfarbe, Tagesplanung
- **working_hours_changes** - Historie von Stundenänderungen
- **time_entries** - Zeiteinträge (Start, Ende nullable für Stempeluhr, Pausen, `sunday_exception_reason` §10 ArbZG)
- **absences** - Abwesenheiten mit Typ, optional Zeitraum und Start-/Endzeit
- **public_holidays** - Bayerische Feiertage
- **change_requests** - Änderungsanträge für Zeiteinträge und Abwesenheiten
- **time_entry_audit_logs** - Audit-Logs für Zeiteinträge
- **error_logs** - Backend-Fehler mit Deduplizierung, Status und GitHub-Verlinkung

### Migrationen

Die Datenbank wird beim Start automatisch migriert. Manuelle Migration:

```bash
docker-compose exec backend alembic upgrade head
```

Neue Migration erstellen:

```bash
docker-compose exec backend alembic revision --autogenerate -m "description"
```

**Aktuelle Migrationen (001–030):**
- `001` - Initial Schema (User, TimeEntry, Absence, PublicHoliday)
- `002` - Add track_hours field
- `003` - Add end_date to absences (Zeiträume)
- `004` - Add calendar_color to users
- `005` - Add working_hours_changes table
- `006` - Add work_days_per_week
- `007` - Add change_requests
- `008` - Add time_entry_audit_logs
- `009` - Make end_time nullable (Stempeluhr)
- `010` - Add username field, make email optional
- `011–013` - Vacation carryover deadline, company closures, daily schedule
- `014` - Add error_logs table
- `015` - Add hidden flag to users
- `016` - Add token_version to users (JWT revocation)
- `017` - Add sunday_exception_reason + exempt_from_arbzg (§10/§18 ArbZG)
- `018` - Add is_night_worker to users (§6 ArbZG)
- `019` - Add TOTP 2FA (totp_secret, totp_enabled)
- `020` - Add deactivated_at to users (14-Tage-Grace-Period DSGVO)
- `021–026` - Multi-Tenant RLS, Tenant-Modell, RLS-Policies
- `027` - RLS-Policies für alle Tabellen
- `028` - Review-Findings (ConfigDict, Type Escapes)
- `029` - VacationRequest absence_type Erweiterung
- `030` - Absence Start-/Endzeit + Change Request Absence-Felder

## Entwicklung

### Backend lokal ausführen

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend lokal ausführen

```bash
cd frontend
npm install
npm run dev
```

### Logs anzeigen

```bash
docker-compose logs -f backend
docker-compose logs -f frontend
```

## API Dokumentation

Die vollständige API-Dokumentation ist verfügbar unter:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### Wichtige Endpoints

**Authentifizierung:**
- `POST /api/auth/login` - Login
- `GET /api/auth/me` - Aktueller User
- `PUT /api/auth/password` - Passwort ändern

**Stempeluhr:**
- `GET /api/time-entries/clock-status` - Aktueller Stempel-Status
- `POST /api/time-entries/clock-in` - Einstempeln
- `POST /api/time-entries/clock-out` - Ausstempeln (mit Pauseneingabe)

**Zeiterfassung:**
- `GET /api/time-entries` - Liste der Einträge
- `POST /api/time-entries` - Neuer Eintrag
- `PUT /api/time-entries/{id}` - Bearbeiten
- `DELETE /api/time-entries/{id}` - Löschen

**Abwesenheiten:**
- `GET /api/absences` - Liste
- `POST /api/absences` - Neue Abwesenheit (auch Zeiträume)
- `DELETE /api/absences/{id}` - Löschen
- `GET /api/absences/calendar` - Kalender-Ansicht

**Admin:**
- `GET /api/admin/users` - Alle Benutzer
- `POST /api/admin/users` - User anlegen
- `PUT /api/admin/users/{id}` - User bearbeiten
- `GET /api/admin/users/{id}/working-hours-changes` - Stundenhistorie
- `POST /api/admin/users/{id}/working-hours-changes` - Stundenänderung erfassen
- `GET /api/admin/reports/monthly` - Monatsberichte
- `GET /api/admin/reports/export?month=YYYY-MM` - Monatsexport Excel
- `GET /api/admin/reports/export-yearly?year=YYYY` - Jahresexport detailliert
- `GET /api/admin/reports/export-yearly-classic?year=YYYY` - Jahresexport classic
- `GET /api/admin/reports/rest-time-violations?year=YYYY` - Ruhezeitverstöße §5 ArbZG
- `GET /api/admin/reports/sunday-summary?year=YYYY` - Sonntagsarbeit §11 ArbZG
- `GET /api/admin/reports/night-work-summary?year=YYYY` - Nachtarbeit §6 ArbZG
- `GET /api/admin/reports/compensatory-rest?year=YYYY` - Ersatzruhetag-Tracking §11 ArbZG

**Dashboard:**
- `GET /api/dashboard` - Dashboard-Daten
- `GET /api/dashboard/overtime` - Überstundenkonto mit Historie
- `GET /api/dashboard/vacation` - Urlaubskonto

## Deployment

### Produktions-Deployment

1. Server mit Docker & Docker Compose vorbereiten
2. Repository klonen
3. `.env` mit Produktions-Credentials erstellen
4. SSL-Zertifikate unter `ssl/` ablegen (`cert.pem`, `key.pem`, `nginx-ssl.conf`)
5. Container mit SSL starten:

```bash
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build
```

**Updates einspielen:**
```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build
```

Datenbank-Migrationen werden automatisch beim Start ausgeführt.

### Backup

**Datenbank-Backup:**
```bash
docker-compose exec db pg_dump -U praxiszeit praxiszeit > backup.sql
```

**Datenbank-Restore:**
```bash
docker-compose exec -T db psql -U praxiszeit praxiszeit < backup.sql
```

## Compliance & Audits

PraxisZeit wird regelmäßig auf Sicherheit, Datenschutz und Arbeitszeitrecht geprüft. Alle Audit-Berichte und Prozessdokumentationen liegen in `docs/specs/`:

| Bereich | Ordner | Status |
|---------|--------|--------|
| Security (OWASP) | `docs/specs/security/` | ✓ 23 Findings behoben |
| DSGVO | `docs/specs/dsgvo/` | ✓ Konform (Art. 5/6/9/15/17/20/25/32) |
| ArbZG §3–§18 | `docs/specs/arbzg/` | ✓ Konform (§2–§18 geprüft, 4 Reviews) |

Jeder Ordner enthält eine `HOWTO.md` mit dem Audit-Prozess, dem Claude-Prompt zur Erstellung und der Regel: **nach jedem Audit → aktualisierten Report erzeugen**.

## Support & Dokumentation

- **CLAUDE.md** - Umfangreiche Projekt-Dokumentation für Entwickler
- **docs/handbuch/** - Markdown-Handbücher für Mitarbeiter und Admins
- **docs/generated/** - Generierte PDF/HTML-Handbücher (lokal, nicht im Repo)
- **docs/ARC42.md** - Architekturdokumentation (ARC42-Format)
- **docs/INSTALLATION.md** - Detaillierte Installationsanleitung
- **docs/specs/** - Audit-Berichte (Security, DSGVO, ArbZG)
- **API Docs** - http://localhost:8000/docs
- **GitHub Issues** - https://github.com/phash/praxiszeit/issues

## Lizenz

Proprietär - Alle Rechte vorbehalten
