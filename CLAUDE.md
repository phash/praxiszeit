# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# PraxisZeit - Zeiterfassungssystem

Ein vollständiges Zeiterfassungssystem für Arztpraxen und kleine Unternehmen.

## 🚀 Projekt-Übersicht

**Repository:** https://github.com/phash/praxiszeit

**Technologie-Stack:**
- Frontend: React 18 + TypeScript + Tailwind CSS + Vite
- Backend: FastAPI (Python 3.12) + PostgreSQL 16
- Deployment: Docker + Docker Compose
- Authentication: JWT tokens
- ORM: SQLAlchemy + Alembic Migrations

## 📋 Hauptfunktionen

### Für Mitarbeiter
- ✅ **Zeiterfassung**: Wochenansicht mit Start/End-Zeit, Pausen, Notizen
- ✅ **Soll/Ist-Vergleich**: Automatische Berechnung von Über-/Unterstunden
- ✅ **Dashboard**: Übersicht über Arbeitszeiten, Urlaubskonto, Überstunden
- ✅ **Abwesenheiten**: Urlaub, Krankheit, Fortbildung, Sonstiges
- ✅ **Zeitraum-Erfassung**: Mehrere Tage auf einmal eintragen
- ✅ **Profilseite**: Passwort ändern, persönliche Daten einsehen

### Für Administratoren
- ✅ **Benutzerverwaltung**: Anlegen, Bearbeiten, Deaktivieren von Mitarbeitern
- ✅ **Arbeitszeiten-Historie**: Stundenänderungen nachverfolgen (z.B. Teilzeit-Anpassungen)
- ✅ **Urlaubsübersicht**: Budget, Verbrauch und Resturlaub pro Mitarbeiter mit Ampel-System
- ✅ **Kalenderfarben**: Individuelle Farben für jeden MA im Abwesenheitskalender
- ✅ **Admin Dashboard**: Teamübersicht mit allen Mitarbeitern und deren Stundensalden
- ✅ **Jahresübersicht**: Abwesenheitstage nach Typ (Urlaub, Krank, Fortbildung)
- ✅ **Detailansicht**: Zeiteinträge und Abwesenheiten pro Mitarbeiter
- ✅ **Berichte-Seite** mit drei Export-Optionen:
  - Monatsreport (detailliert mit täglichen Einträgen)
  - Jahresreport Classic (kompakte 12-Monats-Übersicht)
  - Jahresreport Detailliert (365 Tage pro MA)
- ✅ **Stundenzählung deaktivieren**: Für Mitarbeiter ohne Arbeitszeiterfassung
- ✅ **Abwesenheitskalender**: Team-Übersicht aller Abwesenheiten mit Farbcodierung

### Besondere Features
- 🗓️ **Feiertage**: Automatische Berücksichtigung gesetzlicher Feiertage
- 📅 **Wochenenden ausschließen**: Bei Zeiträumen automatisch nur Werktage
- 🔒 **Rollensystem**: Admin vs. Employee mit unterschiedlichen Berechtigungen
- 📊 **Urlaubskonto**: Automatische Berechnung mit Vorjahresübertrag
- 🎨 **Responsive Design**: Hamburger-Menu + Card-Layouts auf Mobile
- 🔔 **Toast-Notifications**: Styled Benachrichtigungen statt browser-native alert/confirm
- ❤️ **Health Check**: `/api/health` Endpoint mit DB-Connectivity-Test
- 🌐 **CORS konfigurierbar**: Via `CORS_ORIGINS` Umgebungsvariable

## 🏗️ Architektur und Code-Organisation

### Backend-Architektur (FastAPI)

**Layered Architecture:**
```
routers/ → services/ → models/ → database
  ↓          ↓          ↓
schemas/  (business  (ORM)
          logic)
```

**Key Directories:**
- `models/` - SQLAlchemy ORM Models (User, TimeEntry, Absence, PublicHoliday, WorkingHoursChange)
- `routers/` - FastAPI Endpoints (auth, admin, time_entries, absences, dashboard, holidays, reports)
- `schemas/` - Pydantic Request/Response Models (separate from ORM models)
- `services/` - Business Logic Layer:
  - `auth_service.py` - Password hashing, JWT token generation
  - `calculation_service.py` - **Core business logic** for Soll/Ist calculations, overtime, vacation
  - `export_service.py` - Excel export generation (monthly, yearly classic, yearly detailed)
  - `holiday_service.py` - Public holiday management via workalendar
- `middleware/` - Auth middleware for dependency injection
- `config.py` - Environment variables via pydantic-settings
- `database.py` - SQLAlchemy engine and session management
- `main.py` - FastAPI app with lifespan events (startup: migrations, admin creation, holiday sync)

**Critical Patterns:**
1. **Historical Calculations:** `calculation_service.get_weekly_hours_for_date()` gets weekly hours for any date by checking `working_hours_changes` table. Always iterate day-by-day for accurate calculations.
2. **Session Management:** Use dependency injection `Depends(get_db)` for routes. Never reuse objects across sessions.
3. **Date Ranges:** When creating absences with `end_date`, backend creates separate entries for each weekday (Mon-Fri), excluding weekends and public holidays.
4. **Type Safety:** Use `float` not `Decimal` in Pydantic schemas (Decimal serializes as string in JSON).

### Frontend-Architektur (React + TypeScript)

**Structure:**
```
src/
├── pages/           # Full page components (Dashboard, TimeTracking, Profile, etc.)
│   └── admin/       # Admin-only pages (Users, Dashboard, Reports)
├── components/      # Shared UI components (Button, Badge, ConfirmDialog, FormInput, etc.)
├── contexts/        # React Contexts (ToastContext)
├── hooks/           # Custom hooks (useConfirm)
├── constants/       # Shared constants (absenceTypes)
├── stores/          # Zustand state management
│   └── authStore.ts # Auth state (user, token, login/logout)
├── api/
│   └── client.ts    # Axios instance with auth interceptor
├── App.tsx          # Router setup with protected routes (wrapped in ToastProvider)
└── main.tsx         # Entry point
```

**Key Patterns:**
1. **State Management:** Zustand for auth state only. Server state is fetched per-page (no global cache).
2. **Protected Routes:** Check `authStore` for token, redirect to login if missing.
3. **Role-Based UI:** Admin routes check `user.role === 'admin'`.
4. **API Client:** Axios instance in `api/client.ts` adds Bearer token to all requests.
5. **Date Handling:** Use date-fns for formatting, native `<input type="date">` for inputs (YYYY-MM-DD format).

### Projekt-Struktur

```
praxiszeit/
├── backend/
│   ├── app/
│   │   ├── models/          # SQLAlchemy Models
│   │   ├── routers/         # FastAPI Endpoints
│   │   ├── schemas/         # Pydantic Schemas
│   │   ├── services/        # Business Logic Layer (calculation, export, auth, holiday)
│   │   ├── middleware/      # Auth Middleware
│   │   ├── config.py        # Settings via pydantic-settings
│   │   ├── database.py      # SQLAlchemy setup
│   │   └── main.py          # FastAPI app with lifespan
│   ├── alembic/
│   │   ├── env.py           # Alembic configuration
│   │   └── versions/        # Migration files
│   ├── tests/               # Pytest tests
│   │   ├── conftest.py      # Test fixtures
│   │   ├── test_auth.py     # Auth endpoint tests
│   │   └── test_calculations.py  # Business logic tests
│   ├── create_test_data.py  # Test data generator
│   ├── requirements.txt     # Python dependencies
│   ├── pytest.ini           # Pytest configuration
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── pages/           # Full page components
│       │   └── admin/       # Admin pages
│       ├── components/      # Shared UI components (Button, Badge, ConfirmDialog, etc.)
│       ├── contexts/        # React Contexts (ToastContext)
│       ├── hooks/           # Custom hooks (useConfirm)
│       ├── constants/       # Shared constants (absenceTypes)
│       ├── stores/          # Zustand stores
│       ├── api/             # API client
│       ├── App.tsx          # Router (wrapped in ToastProvider)
│       └── main.tsx         # Entry point
├── docker-compose.yml       # Multi-container orchestration
├── .env.example             # Environment template
├── README.md                # User documentation
├── CLAUDE.md                # This file
└── UX_ROADMAP.md            # UX/UI-Roadmap (alle 6 Phasen abgeschlossen)

```

## 🔧 Entwicklung

### Lokale Entwicklung starten
```bash
docker-compose up -d
```

Services:
- Frontend: http://localhost (Port 80)
- Backend: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Dienste stoppen
```bash
docker-compose down
```

### Logs ansehen
```bash
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f db
```

### Backend lokal (ohne Docker)
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Frontend lokal (ohne Docker)
```bash
cd frontend
npm install
npm run dev  # Starts on http://localhost:5173
```

### Database Migrations

**IMPORTANT:** Migrationen müssen auf dem Host erstellt werden, BEVOR Container rebuildet werden. Migration-Files gehen sonst beim Rebuild verloren.

```bash
# 1. Migration erstellen (während Container läuft)
docker-compose exec backend alembic revision --autogenerate -m "add new field"

# 2. Migration-File wird in backend/alembic/versions/ erstellt
# 3. Migration wird automatisch beim nächsten Container-Start ausgeführt

# Manuelle Migration ausführen
docker-compose exec backend alembic upgrade head

# Migration rückgängig machen
docker-compose exec backend alembic downgrade -1

# Migrations-Historie anzeigen
docker-compose exec backend alembic history
```

### Testing

**Backend Tests:**
```bash
# In Docker
docker-compose exec backend pytest
docker-compose exec backend pytest -v  # Verbose
docker-compose exec backend pytest tests/test_auth.py  # Einzelne Datei
docker-compose exec backend pytest -k test_login  # Einzelner Test

# Lokal (mit aktiviertem venv)
cd backend
pytest
pytest --cov=app --cov-report=html  # Mit Coverage
```

**Frontend Linting:**
```bash
# In Docker
docker-compose exec frontend npm run lint

# Lokal
cd frontend
npm run lint
npm run build  # TypeScript Compilation Check
```

### Test-Daten generieren
```bash
docker-compose exec backend python create_test_data.py
```
Erstellt 4 Mitarbeiterinnen mit vollständigen Zeiteinträgen und Abwesenheiten für 2026.

## 🗄️ Datenbank-Schema

**PostgreSQL 16** mit folgenden Haupttabellen:

### users
```sql
id, username (unique), email, password_hash, first_name, last_name,
role (admin/employee), weekly_hours, vacation_days, work_days_per_week,
track_hours (bool), calendar_color, use_daily_schedule,
hours_monday..hours_friday, token_version (int, default 0),
exempt_from_arbzg (bool, default false),
is_active, is_hidden, vacation_carryover_deadline,
created_at, updated_at
```
- `track_hours=False`: Deaktiviert Arbeitszeiterfassung (Soll-Stunden = 0)
- `calendar_color`: Hex-Farbe für Abwesenheitskalender
- `token_version`: Wird inkrementiert um alle JWT-Tokens zu invalidieren
- `exempt_from_arbzg=True`: Überspringt alle §3/§4/§14-Prüfungen und Warnungen (§18 ArbZG – leitende Angestellte)
- **Indexes:** username (unique), email, role

### working_hours_changes
```sql
id, user_id (FK), weekly_hours, effective_from (date),
note, created_at
```
- Historie von Arbeitszeitenänderungen (z.B. Teilzeit-Anpassungen)
- **Wichtig:** Sortierung nach `effective_from DESC` für korrekte Historie
- **Indexes:** user_id, effective_from

### time_entries
```sql
id, user_id (FK), date, start_time, end_time,
break_minutes, notes, sunday_exception_reason (nullable text),
created_at, updated_at
```
- Tägliche Zeiteinträge (von-bis mit Pausen)
- Berechnete Arbeitszeit: `(end_time - start_time) - break_minutes`
- `sunday_exception_reason`: Optionaler Dokumentationstext für §10-ArbZG-Ausnahme bei Sonn-/Feiertagsarbeit
- **Indexes:** user_id, date, (user_id, date) composite

### absences
```sql
id, user_id (FK), date, end_date (nullable),
type (vacation/sick/training/other), notes,
created_at, updated_at
```
- `end_date=NULL`: Einzelner Tag
- `end_date!=NULL`: Zeitraum (alle Einträge in Zeitraum speichern Original-end_date)
- **Indexes:** user_id, date, type, (user_id, date) composite

### public_holidays
```sql
id, date, name, state (Bayern), created_at
```
- Automatisch von workalendar synchronisiert (Germany Bavaria)
- Wird beim App-Start für current/next year aktualisiert
- **Indexes:** date, state

### Migrationen (Alembic)
- `001_initial`: Initial Schema (User, TimeEntry, Absence, PublicHoliday)
- `002_track_hours`: Add `track_hours` field (Stundenzählung deaktivierbar)
- `003_end_date`: Add `end_date` to absences (Zeiträume)
- `004_calendar_color`: Add `calendar_color` to users (Farbcodierung im Kalender)
- `005_working_hours_changes`: Add working_hours_changes table (Arbeitszeiten-Historie)
- `006_add_work_days_per_week`: Add `work_days_per_week` to users (flexible Arbeitstage)
- `007` - `014`: Various feature migrations (change_requests, audit_log, company_closures, error_logs, etc.)
- `015_add_token_version`: Add `token_version` to users (JWT revocation support)
- `016_add_sunday_exception_reason_and_arbzg_exempt`: Add `sunday_exception_reason` to time_entries + `exempt_from_arbzg` to users (§10/§18 ArbZG)

### Datenbank-Operationen

**Backup:**
```bash
docker-compose exec db pg_dump -U praxiszeit praxiszeit > backup_$(date +%Y%m%d).sql
```

**Restore:**
```bash
docker-compose exec -T db psql -U praxiszeit praxiszeit < backup_20260209.sql
```

**Shell:**
```bash
docker-compose exec db psql -U praxiszeit praxiszeit
```

**Reset (Vorsicht!):**
```bash
docker-compose down -v  # Löscht Volumes!
docker-compose up -d    # Erstellt frische DB
```

## 👤 Standard-Benutzer

Nach dem ersten Start existieren folgende Benutzer:
- **Admin**: admin@praxis.de
- **Test-Admin** (für Screenshots): admin@example.com / admin123
- **Mitarbeiter**: manuel@klotz-roedig.de

## 📦 Dependencies

### Backend
- fastapi + uvicorn
- sqlalchemy + alembic
- psycopg2-binary
- python-jose (JWT)
- passlib + bcrypt
- pydantic
- openpyxl (Excel Export)

### Frontend
- react + react-dom
- react-router-dom
- zustand (State Management)
- axios
- date-fns
- lucide-react (Icons)
- tailwindcss

## 🧮 Business Logic (calculation_service.py)

**Kernfunktionen für Soll/Ist-Berechnungen:**

### `get_weekly_hours_for_date(db, user, date) -> Decimal`
Ermittelt die Wochenstunden, die an einem bestimmten Datum galten (berücksichtigt Historie).
```python
# Findet die letzte Änderung vor/am Datum
change = db.query(WorkingHoursChange).filter(
    effective_from <= date
).order_by(effective_from.desc()).first()
return change.weekly_hours if change else user.weekly_hours
```

### `get_daily_target(user, weekly_hours) -> Decimal`
Berechnet Soll-Stunden pro Tag (Wochenstunden / 5).
- Returns `Decimal('0')` wenn `user.track_hours == False`

### `calculate_monthly_stats(db, user, year, month) -> Dict`
**Zentrale Funktion für Monatsberechnungen:**
1. Iteriert über jeden Tag im Monat
2. Für jeden Tag:
   - Prüft ob Wochenende → skip
   - Prüft ob Feiertag → skip
   - Prüft ob Abwesenheit → add to `absence_hours`
   - Holt Zeiteinträge → add to `actual_hours`
   - Berechnet `daily_target` mit historischen Wochenstunden
3. Berechnet `balance = actual_hours - target_hours`

**Wichtig:** Verwendet `get_weekly_hours_for_date()` für **jeden Tag**, nicht Monatsmittelwerte!

### `calculate_overtime_history(db, user, months=6) -> List[Dict]`
Berechnet Überstunden-Historie über mehrere Monate.
```python
for month in last_n_months:
    stats = calculate_monthly_stats(db, user, year, month)
    overtime_history.append({
        'month': f'{year}-{month:02d}',
        'balance': stats['balance']
    })
```

### `calculate_vacation_account(db, user, year) -> Dict`
Berechnet Urlaubskonto:
1. Budget: `user.vacation_days * (user.weekly_hours / 5)`
2. Used: Summe aller Urlaubs-Abwesenheiten in Stunden
3. Remaining: `budget - used`

**Farb-Logik (Ampel-System):**
- Grün: `remaining >= budget * 0.5`
- Gelb: `remaining >= budget * 0.25`
- Rot: `remaining < budget * 0.25`

## 📊 Export Service (export_service.py)

Generiert Excel-Exports mit `openpyxl`.

### `generate_monthly_report(db, year, month) -> BytesIO`
**Detaillierter Monatsreport:**
- Ein Tab pro Mitarbeiter
- Zeile pro Tag: Datum, Wochentag, Start, Ende, Pause, Ist, Soll, Abwesenheit
- Summenzeile: Gesamt-Ist, Gesamt-Soll, Balance, Urlaubstage

### `generate_yearly_classic_report(db, year) -> BytesIO`
**Kompakte Jahresübersicht (12 Monate):**
- Ein Tab pro Mitarbeiter
- Zeile pro Monat: Monat, Soll, Ist, Balance, Urlaub, Krank, Fortbildung
- **Performance:** ~17KB, schnell

### `generate_yearly_detailed_report(db, year) -> BytesIO`
**Detaillierte Jahresübersicht (365 Tage):**
- Ein Tab pro Mitarbeiter
- Zeile pro Tag im ganzen Jahr
- **Performance:** ~108KB, dauert 3-5s

**Export-Pattern:**
```python
workbook = Workbook()
for user in users:
    sheet = workbook.create_sheet(f"{user.first_name} {user.last_name}")
    # ... fill data
output = BytesIO()
workbook.save(output)
output.seek(0)
return output
```

## 🎯 API Endpoints

### Authentication
- `POST /api/auth/login` - Login mit Email/Passwort → JWT Token
- `GET /api/auth/me` - Aktueller User (requires auth)
- `PUT /api/auth/password` - Passwort ändern

### Time Entries
- `GET /api/time-entries?user_id={id}&start_date={date}&end_date={date}` - Gefilterte Liste
- `POST /api/time-entries` - Neuer Eintrag
- `PUT /api/time-entries/{id}` - Bearbeiten (nur eigene oder als Admin)
- `DELETE /api/time-entries/{id}` - Löschen

### Absences
- `GET /api/absences?user_id={id}&month={YYYY-MM}` - Liste
- `POST /api/absences` - Neue Abwesenheit (wenn `end_date`: erstellt Range-Einträge)
- `DELETE /api/absences/{id}` - Löschen
- `GET /api/absences/calendar?year={YYYY}&month={MM}` - Kalender für alle Mitarbeiter

### Dashboard
- `GET /api/dashboard` - Stats für aktuellen User (current month, overtime, vacation)
- `GET /api/dashboard/overtime?months={n}` - Überstunden-Historie
- `GET /api/dashboard/vacation?year={YYYY}` - Urlaubskonto

### Admin - Users
- `GET /api/admin/users?include_inactive={bool}` - Alle Benutzer
- `POST /api/admin/users` - User anlegen
- `PUT /api/admin/users/{id}` - User bearbeiten (inkl. track_hours, calendar_color)
- `GET /api/admin/users/{id}/working-hours-changes` - Stundenhistorie
- `POST /api/admin/users/{id}/working-hours-changes` - Neue Stundenänderung

### Admin - Reports & Exports
- `GET /api/admin/reports/monthly?year={YYYY}&month={MM}` - Monatsberichte (JSON)
- `GET /api/admin/reports/export?month={YYYY-MM}` - Excel Monatsexport
- `GET /api/admin/reports/export-yearly?year={YYYY}` - Excel Jahresexport (detailliert)
- `GET /api/admin/reports/export-yearly-classic?year={YYYY}` - Excel Jahresexport (classic)
- `GET /api/admin/reports/rest-time-violations?year={YYYY}` - Ruhezeitverstöße §5 ArbZG
- `GET /api/admin/reports/sunday-summary?year={YYYY}` - Sonntagsarbeit §11 ArbZG (15-freie-Sonntage)
- `GET /api/admin/reports/night-work-summary?year={YYYY}` - Nachtarbeit §6 ArbZG (Nachtarbeitnehmer ≥48 Tage)
- `GET /api/admin/reports/compensatory-rest?year={YYYY}` - Ersatzruhetag-Tracking §11 ArbZG (2/8 Wochen)

### Admin - Dashboard
- `GET /api/admin/dashboard` - Teamübersicht mit allen Mitarbeitern und deren Stats

### Holidays
- `GET /api/holidays?year={YYYY}` - Feiertage für Jahr

## 🔐 Sicherheit

**Umfassendes Security Audit durchgeführt am 2026-02-20** (23 Findings, alle behoben).
Berichte und Prozess: `specs/security/` → `HOWTO.md` beschreibt Audit-Durchführung und Prompt.

### Authentifizierung & Token
- Passwörter mit bcrypt gehasht (`passlib[bcrypt]`, 72-Byte-Truncation)
- JWT Tokens mit HS256 Signatur (`python-jose`)
- **Token-Revocation** via `token_version` Feld auf User-Model (in JWT als `tv` Claim)
  - Inkrementiert bei: Passwortänderung, Deaktivierung, Admin-Set-Password
  - Middleware + Refresh-Endpoint validieren `tv` gegen DB
- **Rate Limiting** via `slowapi`: Login 5/min, Refresh 10/min, PW-Change 3/min
- **Passwort-Komplexität**: Min. 10 Zeichen + Grossbuchstabe + Kleinbuchstabe + Ziffer
- Role-based Access Control (Admin/Employee via `UserRole` Enum)

### Konfigurationssicherheit
- **SECRET_KEY**: Validierung beim Start (min. 32 Zeichen, rejected schwache/Default-Werte)
- **CORS**: Default `http://localhost,http://localhost:5173` (nicht mehr `*`)
  - Warnung bei Wildcard, Credentials nur mit spezifischen Origins
- **ENVIRONMENT**: `development` (default) oder `production` (deaktiviert Swagger/ReDoc)
- **GRAFANA_ADMIN_PASSWORD**: Pflichtfeld, kein Default-Fallback

### Infrastruktur
- Backend-Container läuft als `appuser` (non-root)
- `--forwarded-allow-ips` auf private Netzwerke eingeschränkt
- Nginx: CSP, Referrer-Policy, X-Frame-Options, X-Content-Type-Options
- `/metrics` Endpoint extern blockiert (nur Docker-interner Zugriff)
- `client_max_body_size 1M` in nginx
- Kein API-Caching im Service Worker (sensible Daten)
- Cache-Cleanup bei Logout

### Security Checklist für Production
- [x] `SECRET_KEY` stark generiert (128 Hex-Zeichen) + Startup-Validierung
- [x] `CORS_ORIGINS` auf spezifische Origins gesetzt (Default: localhost)
- [x] Rate Limiting auf Auth-Endpoints aktiv
- [x] Token-Revocation bei Passwortänderung/Deaktivierung
- [x] Passwort-Komplexitätsanforderungen
- [x] Container als non-root User
- [x] Security Headers (CSP, Referrer-Policy, HSTS in SSL)
- [x] Swagger/ReDoc deaktivierbar via ENVIRONMENT=production
- [x] `.env` nicht in Git (`.gitignore`)
- [ ] `CORS_ORIGINS` auf Produktions-Domain setzen (z.B. `https://praxis.example.com`)
- [ ] Admin-Passwort ändern (Startup-Warnung wenn schwach)
- [ ] HTTPS via SSL-Konfiguration aktivieren
- [ ] `ENVIRONMENT=production` in Produktions-`.env` setzen

## ⚖️ ArbZG-Compliance

Vollständige Dokumentation: `specs/arbzg/arbzg-compliance.md` | Audit-Prozess: `specs/arbzg/HOWTO.md`

### Implementierte Checks (alle Eingabepfade: create/update/clock_out/admin/change_requests)

| § | Implementierung | Konstante/Funktion |
|---|----------------|-------------------|
| §3 | 8h-Warnung + 10h-Hard-Stop täglich | `MAX_DAILY_HOURS_WARN=8`, `MAX_DAILY_HOURS_HARD=10` in `time_entries.py` |
| §4 | >6h→30min + >9h→45min Pause | `validate_daily_break()` in `break_validation_service.py` |
| §5 | 11h-Mindestruhezeit | `check_rest_time_violations()` in `rest_time_service.py` |
| §6 | Nachtarbeit 23–6 Uhr | `_is_night_work()` in `time_entries.py`, Report: `/api/admin/reports/night-work-summary` |
| §10 | Ausnahmegrund-Dokumentation | `sunday_exception_reason` Feld auf `TimeEntry` |
| §11 | 15-freie-Sonntage + Ersatzruhetage | Reports: `sunday-summary`, `compensatory-rest` |
| §14 | 48h-Wochenwarnung | `MAX_WEEKLY_HOURS_WARN=48`, `_calculate_weekly_net_hours()` |
| §18 | exempt_from_arbzg-Flag | `User.exempt_from_arbzg` → bypassed alle Checks |

### Warnungs-Flags in `TimeEntryResponse.warnings`
- `DAILY_HOURS_WARNING` – Tageszeit > 8h (§3)
- `WEEKLY_HOURS_WARNING` – Wochenzzeit > 48h (§14)
- `SUNDAY_WORK` – Sonntagsarbeit (§9)
- `HOLIDAY_WORK` – Feiertagsarbeit (§9)

### exempt_from_arbzg-Muster
```python
exempt = current_user.exempt_from_arbzg
if not exempt:
    # §4 Pausenpflicht
    break_error = validate_daily_break(...)
    # §3 Tageshöchstgrenze
    if daily_hours > MAX_DAILY_HOURS_HARD: raise HTTPException(422, ...)
    # §14 Wochenarbeitszeit
    if weekly_hours > MAX_WEEKLY_HOURS_WARN: warnings.append("WEEKLY_HOURS_WARNING")
```

## 🐛 Troubleshooting

### Backend startet nicht

**Problem:** "Database connection failed"
```bash
# Prüfe ob DB läuft
docker-compose ps db
# Sollte "Up (healthy)" zeigen

# Prüfe DB Logs
docker-compose logs db

# Prüfe Credentials in .env
cat .env | grep POSTGRES
```

**Problem:** "Migration failed"
```bash
# Manuell Migrationen ausführen
docker-compose exec backend alembic upgrade head

# Migration-Historie prüfen
docker-compose exec backend alembic current

# Falls kaputt: Reset
docker-compose exec backend alembic downgrade base
docker-compose exec backend alembic upgrade head
```

**Problem:** "Admin user already exists" aber Login funktioniert nicht
```bash
# Passwort-Hash prüfen
docker-compose exec backend python -c "
from app.database import SessionLocal
from app.models import User
db = SessionLocal()
admin = db.query(User).filter(User.email=='admin@praxis.de').first()
print(f'Email: {admin.email}')
print(f'Has password_hash: {bool(admin.password_hash)}')
print(f'Is active: {admin.is_active}')
"

# Passwort neu setzen
docker-compose exec backend python -c "
from app.database import SessionLocal
from app.models import User
from app.services.auth_service import hash_password
db = SessionLocal()
admin = db.query(User).filter(User.email=='admin@praxis.de').first()
admin.password_hash = hash_password('new_password')
db.commit()
print('Password updated!')
"
```

### Frontend zeigt nur weißen Screen

**Problem:** Frontend Build fehlgeschlagen
```bash
# Logs prüfen
docker-compose logs frontend

# Manuell bauen
docker-compose exec frontend npm run build

# Node Modules neu installieren
docker-compose exec frontend rm -rf node_modules
docker-compose exec frontend npm install
```

**Problem:** API-Calls schlagen fehl (CORS)
```bash
# Browser DevTools → Network Tab prüfen
# Sollte sehen: OPTIONS preflight, dann POST/GET

# Backend CORS-Config prüfen in app/main.py
# allow_origins sollte Frontend-URL enthalten
```

### Berechnungen stimmen nicht

**Problem:** Überstunden falsch nach Stundenänderung
```bash
# Prüfe working_hours_changes Tabelle
docker-compose exec backend python -c "
from app.database import SessionLocal
from app.models import WorkingHoursChange
db = SessionLocal()
changes = db.query(WorkingHoursChange).order_by(WorkingHoursChange.effective_from).all()
for c in changes:
    print(f'{c.effective_from}: {c.weekly_hours}h')
"

# Stelle sicher: calculation_service verwendet get_weekly_hours_for_date()
# NICHT user.weekly_hours direkt!
```

**Problem:** Urlaubskonto falsch
```bash
# Debug-Output
docker-compose exec backend python -c "
from app.database import SessionLocal
from app.models import User
from app.services.calculation_service import calculate_vacation_account
db = SessionLocal()
user = db.query(User).first()
result = calculate_vacation_account(db, user, 2026)
print(result)
"
```

### Excel-Export schlägt fehl

**Problem:** "TypeError: unsupported operand type(s) for +: 'float' and 'Decimal'"
```python
# Lösung: Konsistent float() oder Decimal() verwenden
# ❌ balance = float_value + Decimal('8.0')
# ✅ balance = float_value + float(Decimal('8.0'))
```

**Problem:** Export dauert zu lang (Timeout)
```bash
# Prüfe Export-Typ
# Monthly: <1s
# Yearly Classic: ~2s
# Yearly Detailed: ~5s

# Bei Timeout: Erhöhe Frontend Axios Timeout
# api/client.ts: timeout: 30000  // 30s
```

### Performance-Probleme

**Problem:** Dashboard lädt langsam
```bash
# Enable SQL Query Logging
# In backend/app/database.py:
engine = create_engine(DATABASE_URL, echo=True)  # Shows all queries

# Prüfe auf N+1 Queries
# Lösung: Eager Loading mit .options(joinedload())
```

**Problem:** Datenbank langsam
```bash
# Prüfe Indexes
docker-compose exec db psql -U praxiszeit praxiszeit -c "
SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public';
"

# Sollte haben:
# - users: email (unique)
# - time_entries: user_id, date, (user_id, date) composite
# - absences: user_id, date, (user_id, date) composite
# - working_hours_changes: user_id, effective_from
```

### Test-Daten generieren schlägt fehl

**Problem:** create_test_data.py Fehler
```bash
# Logs prüfen
docker-compose exec backend python create_test_data.py

# Falls DB-Constraint-Fehler: Daten bereits vorhanden
# Lösung: User löschen oder IDs in Script anpassen
```

## 💻 Coding Conventions

### Backend (Python)

**Naming:**
- Models: PascalCase (`User`, `TimeEntry`)
- Functions/Variables: snake_case (`calculate_overtime`, `user_id`)
- Constants: UPPER_SNAKE_CASE (`SECRET_KEY`, `DATABASE_URL`)
- Private methods: `_internal_method()`

**Imports:**
```python
# Standard library
from datetime import date, datetime
from typing import Dict, List, Optional

# Third-party
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

# Local
from app.models import User
from app.schemas import UserResponse
from app.services import calculation_service
```

**Type Hints:**
```python
def calculate_balance(user: User, month: int) -> Dict[str, float]:
    ...

# Optional für nullable values
def get_user(user_id: int) -> Optional[User]:
    ...
```

**Error Handling:**
```python
# FastAPI HTTP Exceptions
if not user:
    raise HTTPException(status_code=404, detail="User not found")

# Validation in Pydantic Schemas
class TimeEntryCreate(BaseModel):
    start_time: time
    end_time: time

    @validator('end_time')
    def end_after_start(cls, v, values):
        if v <= values['start_time']:
            raise ValueError('end_time must be after start_time')
        return v
```

### Frontend (TypeScript/React)

**Naming:**
- Components: PascalCase (`Dashboard`, `TimeEntryForm`)
- Functions/Variables: camelCase (`calculateBalance`, `userId`)
- Constants: UPPER_SNAKE_CASE (`API_BASE_URL`)
- Interfaces: PascalCase with `I` prefix optional (`User` or `IUser`)

**Component Structure:**
```tsx
// 1. Imports
import { useState, useEffect } from 'react'
import { User } from '../types'
import { apiClient } from '../api/client'

// 2. Types/Interfaces
interface DashboardProps {
  userId: number
}

// 3. Component
export default function Dashboard({ userId }: DashboardProps) {
  // 3a. State
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  // 3b. Effects
  useEffect(() => {
    loadUser()
  }, [userId])

  // 3c. Handlers
  const loadUser = async () => {
    const response = await apiClient.get(`/users/${userId}`)
    setUser(response.data)
    setLoading(false)
  }

  // 3d. Render
  if (loading) return <div>Loading...</div>
  return <div>{user?.first_name}</div>
}
```

**API Calls:**
```tsx
// ✅ RICHTIG: async/await mit try/catch
const loadData = async () => {
  try {
    setLoading(true)
    const response = await apiClient.get('/api/dashboard')
    setData(response.data)
  } catch (error) {
    console.error('Failed to load:', error)
    toast.error('Fehler beim Laden')
  } finally {
    setLoading(false)
  }
}

// ❌ FALSCH: Unhandled promises
apiClient.get('/api/dashboard').then(r => setData(r.data))
```

**Date Handling:**
```tsx
import { format, parseISO } from 'date-fns'
import { de } from 'date-fns/locale'

// Display
const formatted = format(parseISO(dateString), 'dd.MM.yyyy', { locale: de })

// Input (native date picker expects YYYY-MM-DD)
<input type="date" value={date} onChange={e => setDate(e.target.value)} />
```

## 📚 Dokumentation

- **API Dokumentation**: http://localhost:8000/docs (Swagger UI - interaktiv)
- **API Alternative**: http://localhost:8000/redoc (ReDoc - statisch, schöner)
- **README.md**: User-facing Dokumentation (Installation, Features)
- **CLAUDE.md**: Diese Datei - Entwickler-Dokumentation
- **ARC42.md**: Architektur-Dokumentation
- **UX_ROADMAP.md**: UX/UI-Roadmap mit Umsetzungsdetails (alle 6 Phasen abgeschlossen)
- **Screenshots**: `../screenshots/` Ordner (außerhalb Repo)

### Audit-Dokumentation (`specs/`)

| Ordner | Inhalt | HOWTO |
|--------|--------|-------|
| `specs/features/` | Feature-Spezifikationen (SDD) | `specs/README.md` |
| `specs/security/` | Security-Audit-Berichte | `specs/security/HOWTO.md` |
| `specs/dsgvo/` | DSGVO-Prüfbericht, DSFA, Verarbeitungsverzeichnis | `specs/dsgvo/HOWTO.md` |
| `specs/arbzg/` | ArbZG-Compliance-Bericht und -Dokumentation | `specs/arbzg/HOWTO.md` |

**Audit-Regel:** Nach jedem Audit und Behebung der Findings → aktualisierten Report erzeugen (alle Findings als „Behoben" markieren, Verdict aktualisieren). Prozess und Prompts stehen in den jeweiligen `HOWTO.md`-Dateien.

## 🐛 Wichtige Patterns und Gotchas

### Pydantic & Type Handling
- **Decimal → Float:** Pydantic serialisiert Python `Decimal` als String in JSON, was Frontend-Fehler mit `.toFixed()` verursacht. **Immer `float` in Response-Schemas verwenden** für numerische Felder.
- **Email Validation:** `EmailStr` validator lehnt `.local` TLD ab (reserviert). Verwende `EmailStr` nur für Produktion, nicht für lokale Test-Adressen.
- **Excel Export:** Decimal/float-Mixing vermeiden (TypeError). Konsistent `float()` konvertieren.

### Historische Berechnungen
```python
# ❌ FALSCH: Monatsmittelwerte
avg_hours = sum(changes) / len(changes)

# ✅ RICHTIG: Tag-für-Tag iterieren
for day in date_range:
    daily_hours = get_weekly_hours_for_date(db, user, day)
    calculate_target(daily_hours)
```
- Immer `calculation_service.get_weekly_hours_for_date()` für jedes Datum aufrufen
- `working_hours_changes` sind nach `effective_from DESC` sortiert
- Erste Änderung vor/am Zieldatum gilt

### Date Range Absences
Wenn User "Zeitraum" checkbox aktiviert und `end_date` setzt:
1. Backend validiert Start < End
2. Erstellt **separate Entries** für jeden Werktag (Mo-Fr)
3. Excluded automatisch Wochenenden (`weekday() >= 5`)
4. Excluded Public Holidays via DB-Join
5. Jeder Entry speichert Original-`end_date` für UI-Display

```python
# backend/app/routers/absences.py
if end_date:
    for single_date in date_range(start, end):
        if single_date.weekday() < 5 and not is_public_holiday(single_date):
            entries.append(Absence(date=single_date, end_date=end_date, ...))
```

### SQLAlchemy Session Management
```python
# ❌ FALSCH: Objekte über Sessions hinweg verwenden
def create_entries(db1: Session):
    user = db1.query(User).first()
    db2 = SessionLocal()
    db2.add(TimeEntry(user=user))  # ERROR!

# ✅ RICHTIG: IDs speichern, neu laden
def create_entries(db1: Session):
    user_id = db1.query(User).first().id
    db2 = SessionLocal()
    user = db2.query(User).get(user_id)
    db2.add(TimeEntry(user=user))
```

### Migration-Workflow in Docker
**KRITISCH:** Migrationen auf Host erstellen, **BEVOR** Container rebuildet werden.

```bash
# 1. Migration erstellen (Container läuft)
docker-compose exec backend alembic revision --autogenerate -m "add field"

# 2. Migration-File erscheint in backend/alembic/versions/ auf HOST
# 3. Git commit (!)
# 4. Rebuild ist jetzt sicher
docker-compose up -d --build

# ❌ FALSCH: Container rebuilden ohne Migration auf Host zu sichern
# → Migration-File geht verloren!
```

### Frontend: Conditional Form Fields
```tsx
// Pattern für Zeitraum-Checkbox in AbsenceCalendarPage
const [isRange, setIsRange] = useState(false)
const [endDate, setEndDate] = useState('')

<input type="checkbox" onChange={e => setIsRange(e.target.checked)} />
{isRange && <input type="date" value={endDate} onChange={...} />}
```

### Excel Export Performance
- **Monthly Report:** ~20KB, <1s
- **Yearly Classic (12 Monate):** ~17KB, ~1-2s
- **Yearly Detailed (365 Tage):** ~108KB, ~3-5s
- Bei großen Exports: Loading-State im Frontend anzeigen
- `openpyxl` Workbook in Memory erstellen, als BytesIO zurückgeben

### Auth & JWT
```python
# JWT Access Token Claims
{
  "sub": str(user.id),      # User UUID
  "role": user.role,         # "admin" or "employee"
  "type": "access",          # Token type
  "tv": user.token_version,  # Token version (for revocation)
  "exp": datetime.now(timezone.utc) + timedelta(minutes=30)
}

# JWT Refresh Token Claims
{
  "sub": str(user.id),
  "type": "refresh",
  "tv": user.token_version,
  "exp": datetime.now(timezone.utc) + timedelta(days=7)
}

# Token Revocation: increment user.token_version to invalidate all tokens
# Middleware validates tv == user.token_version on every request
```

```typescript
// Frontend: Token in Zustand Store + localStorage
authStore.setState({ accessToken, refreshToken, user })

// Axios Interceptor adds Bearer token from localStorage
config.headers.Authorization = `Bearer ${token}`

// 401 Response → auto-refresh via refresh_token → retry original request
```

## 🚀 Deployment

### Production Setup

1. **Server vorbereiten:**
```bash
# Docker & Docker Compose installieren
curl -fsSL https://get.docker.com | sh
```

2. **Repository klonen:**
```bash
git clone https://github.com/phash/praxiszeit
cd praxiszeit
```

3. **Environment konfigurieren:**
```bash
cp .env.example .env
nano .env
```

**Wichtig für Production:**
- `SECRET_KEY`: Generiere mit `openssl rand -hex 32`
- `POSTGRES_PASSWORD`: Starkes Passwort
- `DATABASE_URL`: Matche mit Postgres-Credentials
- `ADMIN_EMAIL/PASSWORD`: Initiale Admin-Zugangsdaten
- `CORS_ORIGINS`: Komma-getrennte Liste erlaubter Origins (z.B. `https://praxis.example.com`)

4. **SSL-Zertifikate ablegen** (für Produktion):
```
ssl/
├── nginx-ssl.conf   # Nginx mit HTTPS-Konfiguration
├── cert.pem         # SSL-Zertifikat
└── key.pem          # Privater Schlüssel
```

5. **Container starten:**
```bash
# Produktion (mit SSL):
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d

# Lokal (ohne SSL):
docker-compose up -d
```

6. **Logs prüfen:**
```bash
docker-compose logs -f
# Sollte zeigen: Migrations, Admin-Erstellung, Holiday-Sync
```

7. **Nginx Reverse Proxy (empfohlen):**
```nginx
server {
    listen 80;
    server_name praxiszeit.example.com;

    location / {
        proxy_pass http://localhost:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Updates deployen (Produktion mit SSL)

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build
```

### Updates deployen (lokal ohne SSL)

```bash
git pull
docker-compose up -d --build
```

**Wichtig:** Migrationen werden automatisch beim Container-Start ausgeführt (siehe `main.py` lifespan).

### Backup-Strategy

**Automatisches Backup (Cron):**
```bash
# /etc/cron.daily/praxiszeit-backup
#!/bin/bash
cd /path/to/praxiszeit
docker-compose exec -T db pg_dump -U praxiszeit praxiszeit | gzip > /backups/praxiszeit_$(date +\%Y\%m\%d).sql.gz
# Alte Backups löschen (älter als 30 Tage)
find /backups -name "praxiszeit_*.sql.gz" -mtime +30 -delete
```

**Manuelles Backup:**
```bash
docker-compose exec db pg_dump -U praxiszeit praxiszeit > backup.sql
```

### Monitoring

**Health Check:**
```bash
curl http://localhost:8000/api/health
# Healthy: {"status": "healthy", "database": "connected"}
# Unhealthy (503): {"status": "unhealthy", "database": "disconnected"}
```

**Container Status:**
```bash
docker-compose ps
# All services should be "Up"
```

**Logs:**
```bash
docker-compose logs --tail=100 backend  # Last 100 lines
docker-compose logs -f --since 1h       # Live logs last hour
```

## 🎨 UX/UI Roadmap

**Status:** UX-Analyse durchgeführt, Kernphasen umgesetzt (Stand: 10.02.2026)

**Erledigte Phasen:**
- ✅ **Phase 0:** Foundation - Toast-System, ConfirmDialog, Shared Components (Button, Badge, FormInput, FormSelect, FormTextarea, LoadingSpinner, MonthSelector, TableSkeleton)
- ✅ **Phase 1:** Mobile Navigation - Hamburger-Menu mit Sidebar, Escape-Key-Support, Route-Change-Close
- ✅ **Phase 2:** Responsive Tables - Card-Layouts auf Mobile für alle Tabellen (TimeTracking, Absences, Users, AdminDashboard)
- ✅ **Phase 3:** Accessibility (A11y) - FocusTrap, ARIA-Rollen, Keyboard-Nav, Label-Input-Verknüpfungen
- ✅ **Phase 4:** Calendar & Date Navigation - MonthSelector-Komponente mit Prev/Next
- ✅ **Phase 5:** Polish – LoadingSpinner überall, label-Input-Verknüpfungen, Farbkonsistenz

**Alle Phasen abgeschlossen** ✅

**Shared Components** (`frontend/src/components/`):
- `ConfirmDialog.tsx` - Styled Bestätigungsdialog (ersetzt native `confirm()`)
- `Button.tsx` - Varianten: primary, secondary, danger, ghost
- `Badge.tsx` - Status-Badges mit Farbcodierung
- `FormInput.tsx`, `FormSelect.tsx`, `FormTextarea.tsx` - Formular-Komponenten
- `LoadingSpinner.tsx`, `TableSkeleton.tsx` - Ladezustands-Anzeigen
- `MonthSelector.tsx` - Monats-Navigation mit Prev/Next

**Hooks** (`frontend/src/hooks/`):
- `useConfirm.ts` - State-Management für ConfirmDialog

**Contexts** (`frontend/src/contexts/`):
- `ToastContext.tsx` - Toast-Provider mit success/error/info/warning

**Vollständige Umsetzungs-Details: `UX_ROADMAP.md`**

## 📝 Future Features (Backlog)

- [ ] Passwort-Reset-Funktion per Email
- [ ] Benachrichtigungen bei Urlaubsantrag
- [ ] PDF-Export für Monatsberichte
- [ ] Mobile App (React Native)
- [ ] 2-Faktor-Authentifizierung
- [ ] Audit Log für Admin-Aktionen
- [ ] Bulk-Import von Zeiteinträgen (CSV)
- [ ] Urlaubsantrag-Workflow (Beantragen → Genehmigen)

## 🎨 Design-System

**Farben:**
- Primary: `#2563EB` (blue-600) → `bg-primary`
- Hover: `#1E40AF` (blue-700) → `hover:bg-primary-dark`
- Light: `#60A5FA` (blue-400) → `bg-primary-light`
- Urlaub: blue
- Krank: red
- Fortbildung: orange
- Sonstiges: gray

**Komponenten:**
- Tailwind CSS Utility Classes
- Lucide React Icons
- Responsive Grid Layout

---

**Entwickelt mit Claude Sonnet 4.5, Sonnet 4.6 & Opus 4.6**
