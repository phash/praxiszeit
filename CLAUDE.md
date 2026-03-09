# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# PraxisZeit - Zeiterfassungssystem

Zeiterfassung für Arztpraxen und kleine Unternehmen. **Repo:** https://github.com/phash/praxiszeit

## Stack
- Frontend: React 18 + TypeScript + Tailwind CSS + Vite
- Backend: FastAPI (Python 3.12) + PostgreSQL 16
- Deployment: Docker + Docker Compose | Auth: JWT | ORM: SQLAlchemy + Alembic

## 🏗️ Architektur

### Backend (`backend/app/`)
```
routers/ → services/ → models/ → database
```
- `models/` – SQLAlchemy ORM (User, TimeEntry, Absence, PublicHoliday, WorkingHoursChange)
- `routers/` – FastAPI Endpoints (auth, admin, time_entries, absences, dashboard, holidays, reports)
- `schemas/` – Pydantic Request/Response Models
- `services/` – Business Logic: `calculation_service.py`, `export_service.py`, `auth_service.py`, `holiday_service.py`, `break_validation_service.py`, `rest_time_service.py`
- `middleware/` – Auth middleware | `config.py` – pydantic-settings | `main.py` – lifespan (migrations, admin, holidays)

### Frontend (`frontend/src/`)
- `pages/` – Full page components; `pages/admin/` – Admin-only pages
- `components/` – Shared UI: Button, Badge, ConfirmDialog, FormInput/Select/Textarea, LoadingSpinner, TableSkeleton, MonthSelector
- `contexts/ToastContext.tsx` – Toast-Provider (success/error/info/warning)
- `hooks/useConfirm.ts` – ConfirmDialog state
- `stores/authStore.ts` – Zustand auth state (token, user, login/logout)
- `api/client.ts` – Axios mit Bearer-Token Interceptor + 401→auto-refresh
- `App.tsx` – Router (wrapped in ToastProvider)

**Key Patterns:**
- Zustand nur für Auth; Server state per-page fetchen (kein globaler Cache)
- Role check: `user.role === 'admin'`
- Dates: date-fns für Display, native `<input type="date">` (YYYY-MM-DD) für Inputs
- API Calls: immer async/await mit try/catch, setLoading(true/false) im finally

## 🔧 Entwicklung

```bash
docker-compose up -d          # Start (Frontend :80, Backend :8000, API-Docs :8000/docs)
docker-compose down           # Stop
docker-compose logs -f backend|frontend|db

# Migrations (KRITISCH: auf Host erstellen, BEVOR Container rebuildet werden!)
docker-compose exec backend alembic revision --autogenerate -m "add field"
docker-compose exec backend alembic upgrade head
docker-compose exec backend alembic downgrade -1

# Tests
docker-compose exec backend pytest [-v] [tests/test_auth.py] [-k test_name]
docker-compose exec frontend npm run lint

# Test-Daten
docker-compose exec backend python create_test_data.py  # 4 MA mit Einträgen für 2026
```

**Lokal ohne Docker:**
```bash
cd backend && python -m venv venv && venv\Scripts\activate && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev  # :5173
```

## 🗄️ Datenbank-Schema

### users
```sql
id, username (unique), email, password_hash, first_name, last_name,
role (admin/employee), weekly_hours, vacation_days, work_days_per_week,
track_hours (bool), calendar_color, use_daily_schedule, hours_monday..hours_friday,
token_version (int), exempt_from_arbzg (bool), is_active, is_hidden,
vacation_carryover_deadline, created_at, updated_at
```
- `track_hours=False` → Soll-Stunden = 0
- `token_version` → JWT-Revocation (inkrementiert bei PW-Änderung/Deaktivierung)
- `exempt_from_arbzg=True` → bypassed §3/§4/§14 (§18 ArbZG – leitende Angestellte)

### working_hours_changes
`id, user_id (FK), weekly_hours, effective_from (date), note, created_at`
– Sortierung nach `effective_from DESC` für korrekte Historie

### time_entries
`id, user_id (FK), date, start_time, end_time, break_minutes, notes, sunday_exception_reason (nullable), created_at, updated_at`
– Arbeitszeit = `(end_time - start_time) - break_minutes`

### absences
`id, user_id (FK), date, end_date (nullable), type (vacation/sick/training/other), notes, created_at, updated_at`
– `end_date≠NULL`: Zeitraum; jeder Eintrag speichert Original-`end_date`

### public_holidays
`id, date, name, state (Bayern), created_at` – auto-sync via workalendar beim Start

### Migrationen
- 001–006: Initial, track_hours, end_date, calendar_color, working_hours_changes, work_days_per_week
- 007–014: change_requests, audit_log, company_closures, error_logs u.a.
- 015: token_version | 016: sunday_exception_reason + exempt_from_arbzg
- 017+: Weitere Feature-Migrationen (aktuell bis 022: Urlaubsantrag-Workflow)

```bash
# DB-Operationen
docker-compose exec db pg_dump -U praxiszeit praxiszeit > backup.sql
docker-compose exec -T db psql -U praxiszeit praxiszeit < backup.sql
docker-compose exec db psql -U praxiszeit praxiszeit  # Shell
```

## 👤 Standard-Benutzer
- Admin: `admin@praxis.de`
- Test-Admin (Screenshots): `admin@example.com` / `admin123`
- Mitarbeiter: `manuel@klotz-roedig.de`

## 🧮 Business Logic (calculation_service.py)

### Kernfunktionen
- **`get_weekly_hours_for_date(db, user, date)`** – Wochenstunden historisch korrekt (letzte `working_hours_changes`-Änderung vor/am Datum)
- **`get_daily_target(user, weekly_hours)`** – Soll/Tag (weekly_hours/5); 0 wenn `track_hours=False`
- **`calculate_monthly_stats(db, user, year, month)`** – Iteriert jeden Tag; skip Wochenende/Feiertag; summiert absence_hours + actual_hours; `balance = actual - target`
- **`calculate_vacation_account(db, user, year)`** – Budget = vacation_days × (weekly_hours/5); Ampel: grün≥50%, gelb≥25%, rot<25%

**KRITISCH:** Immer `get_weekly_hours_for_date()` per Tag aufrufen – NIE Monatsmittelwerte!

## 📊 Export Service (export_service.py)
- `generate_monthly_report` – Ein Tab/MA, Zeile/Tag (~20KB, <1s)
- `generate_yearly_classic_report` – Ein Tab/MA, Zeile/Monat (~17KB, ~2s)
- `generate_yearly_detailed_report` – Ein Tab/MA, Zeile/Tag im ganzen Jahr (~108KB, ~3-5s)

Pattern: `Workbook() → BytesIO → workbook.save(output) → output.seek(0) → return`

## 🎯 API Endpoints

| Gruppe | Endpoints |
|--------|-----------|
| Auth | POST `/api/auth/login`, GET `/api/auth/me`, PUT `/api/auth/password` |
| Time Entries | CRUD `/api/time-entries` (GET mit user_id/start_date/end_date) |
| Absences | CRUD `/api/absences`; GET `/api/absences/calendar?year&month` |
| Dashboard | GET `/api/dashboard`, `/api/dashboard/overtime?months`, `/api/dashboard/vacation?year` |
| Admin Users | CRUD `/api/admin/users`; `/api/admin/users/{id}/working-hours-changes` |
| Admin Reports | `/api/admin/reports/monthly`, `export`, `export-yearly`, `export-yearly-classic` |
| ArbZG Reports | `rest-time-violations`, `sunday-summary`, `night-work-summary`, `compensatory-rest` |
| Admin Dashboard | GET `/api/admin/dashboard` |
| Holidays | GET `/api/holidays?year` |

## 🔐 Sicherheit

**Audit 2026-02-20: 23 Findings, alle behoben.** Docs: `docs/specs/security/`

- bcrypt-Passwörter, JWT HS256, Token-Revocation via `token_version` (`tv`-Claim)
- Access Token: 30min, Refresh Token: 7d
- Rate Limiting (slowapi): Login 5/min, Refresh 10/min, PW-Change 3/min
- Passwort-Komplexität: min 10 Zeichen + Groß/Klein/Ziffer
- SECRET_KEY-Validierung beim Start (≥32 Zeichen)
- CORS Default: `http://localhost,http://localhost:5173` (kein `*`)
- Container als `appuser` (non-root), Nginx Security Headers, `/metrics` intern blockiert

**Production-Checklist (offene Punkte):**
- [ ] `CORS_ORIGINS` auf Produktions-Domain setzen
- [ ] Admin-Passwort ändern
- [ ] HTTPS via `docker-compose.ssl.yml` aktivieren
- [ ] `ENVIRONMENT=production` setzen (deaktiviert Swagger/ReDoc)

## ⚖️ ArbZG-Compliance

Docs: `docs/specs/arbzg/arbzg-compliance.md` | Prozess: `docs/specs/arbzg/HOWTO.md`

| § | Check | Implementierung |
|---|-------|----------------|
| §3 | 8h-Warnung + 10h-Hard-Stop | `MAX_DAILY_HOURS_WARN=8/HARD=10` in `time_entries.py` |
| §4 | >6h→30min, >9h→45min Pause | `validate_daily_break()` in `break_validation_service.py` |
| §5 | 11h-Mindestruhezeit | `check_rest_time_violations()` in `rest_time_service.py` |
| §6 | Nachtarbeit 23–6 Uhr | `_is_night_work()`, Report: `night-work-summary` |
| §10 | Ausnahmegrund-Doku | `sunday_exception_reason` auf `TimeEntry` |
| §11 | 15-freie-Sonntage + Ersatzruhetage | Reports: `sunday-summary`, `compensatory-rest` |
| §14 | 48h-Wochenwarnung | `MAX_WEEKLY_HOURS_WARN=48`, `_calculate_weekly_net_hours()` |
| §18 | Leitende Angestellte | `User.exempt_from_arbzg` → bypassed §3/§4/§14 |

**Warnings in `TimeEntryResponse.warnings`:** `DAILY_HOURS_WARNING`, `WEEKLY_HOURS_WARNING`, `SUNDAY_WORK`, `HOLIDAY_WORK`

**Alle Checks greifen auf allen Eingabepfaden:** create / update / clock_out / admin / change_requests

## 🐛 Wichtige Patterns & Gotchas

### Historische Berechnungen
```python
# ❌ FALSCH: Monatsmittelwerte  # ✅ RICHTIG: Tag-für-Tag
for day in date_range:
    daily_hours = get_weekly_hours_for_date(db, user, day)  # NIE user.weekly_hours direkt!
```

### Date Range Absences
Backend erstellt für `end_date`-Range **separate Einträge** pro Werktag (Mo-Fr), excluded Wochenenden + Feiertage. Jeder Entry speichert Original-`end_date`.

### Pydantic Type Handling
- **Decimal → float:** Pydantic serialisiert `Decimal` als String. **Immer `float` in Response-Schemas.**
- **Excel:** Decimal/float-Mixing → TypeError. Konsistent `float()` konvertieren.

### SQLAlchemy Session Management
```python
# ❌ Objekte über Sessions hinweg verwenden
# ✅ IDs speichern, in neuer Session neu laden
user_id = db1.query(User).first().id
user = db2.query(User).get(user_id)
```

### Migration-Workflow
**KRITISCH:** Migration auf Host erstellen → git commit → dann Container rebuilden. Sonst geht die Migration verloren!
```bash
docker-compose exec backend alembic revision --autogenerate -m "add field"
git add backend/alembic/versions/  && git commit -m "migration"
docker-compose up -d --build
```

### Auth & JWT
```python
# Access Token Claims: sub, role, type="access", tv=token_version, exp=+30min
# Refresh Token Claims: sub, type="refresh", tv, exp=+7d
# Revocation: user.token_version inkrementieren → alle Tokens ungültig
```

## 💻 Coding Conventions

**Backend (Python):** Models=PascalCase, functions/vars=snake_case, constants=UPPER_SNAKE_CASE, private=`_method()`

**Frontend (TypeScript):** Components=PascalCase, functions/vars=camelCase, constants=UPPER_SNAKE_CASE

**Error Handling:** `raise HTTPException(status_code=404, detail="...")` | Pydantic validators für Input-Validierung

## 🐛 Troubleshooting

| Problem | Lösung |
|---------|--------|
| DB connection failed | `docker-compose ps db` (should be healthy), check `.env` POSTGRES_* |
| Migration failed | `alembic upgrade head` manuell; bei kaputtem State: `downgrade base && upgrade head` |
| Login schlägt fehl trotz Admin | PW-Hash neu setzen via Python-Shell in Container |
| White screen | `docker-compose logs frontend`; ggf. `npm run build` oder `rm -rf node_modules && npm install` |
| CORS-Fehler | `app/main.py` allow_origins prüfen |
| Überstunden falsch | `working_hours_changes` prüfen; sicherstellen dass `get_weekly_hours_for_date()` verwendet wird |
| Excel TypeError | Decimal/float-Mixing → `float()` konvertieren |
| Export-Timeout | Yearly Detailed ~5s; Axios timeout auf ≥30s |
| Dashboard langsam | `echo=True` in DB-Engine für Query-Logging; N+1 via joinedload() fixen |

## 🚀 Deployment

```bash
# Produktion (SSL):
cp .env.example .env  # SECRET_KEY, POSTGRES_PASSWORD, CORS_ORIGINS, ADMIN_EMAIL/PASSWORD setzen
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d

# Updates:
git pull && docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d --build

# Backup (täglich via cron):
docker-compose exec -T db pg_dump -U praxiszeit praxiszeit | gzip > backup_$(date +%Y%m%d).sql.gz

# Health Check:
curl http://localhost:8000/api/health
```

## 📚 Dokumentation & Audits

- `docs/ARC42.md` – Architektur | `docs/UX_ROADMAP.md` – UX (alle 6 Phasen abgeschlossen)
- `docs/handbuch/` – Admin- und Mitarbeiter-Handbücher + Screenshots
- `docs/specs/security/` – Security-Audit (HOWTO.md für Prozess)
- `docs/specs/dsgvo/` – DSGVO-Prüfbericht, DSFA, Verarbeitungsverzeichnis
- `docs/specs/arbzg/` – ArbZG-Compliance-Bericht (HOWTO.md für Prozess)
- `docs/specs/features/` – Feature-Spezifikationen (SDD)

**Audit-Regel:** Nach Audit + Fixing → aktualisierten Report erzeugen (Findings als „Behoben", Verdict aktualisieren). Prozess in `HOWTO.md`.

## 🎨 Design-System
- Primary: `#2563EB` (blue-600) | Hover: `#1E40AF` | Light: `#60A5FA`
- Abwesenheitstypen: Urlaub=blue, Krank=red, Fortbildung=orange, Sonstiges=gray
- Icons: Lucide React | CSS: Tailwind Utility Classes

---
**Entwickelt mit Claude Sonnet 4.5, Sonnet 4.6 & Opus 4.6**
