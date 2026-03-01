# ARC42 Architekturdokumentation – PraxisZeit

> Erstellt nach dem arc42-Template (https://arc42.org/overview)
> Version: 1.0 | Stand: Februar 2026

---

## 1. Einführung und Ziele

### 1.1 Aufgabenstellung

PraxisZeit ist ein webbasiertes Zeiterfassungssystem für Arztpraxen und kleine Betriebe. Es ermöglicht:

- **Zeiterfassung**: Mitarbeiter erfassen tägliche Arbeitszeiten (Start, Ende, Pausen)
- **Abwesenheitsverwaltung**: Urlaub, Krankmeldungen, Fortbildungen
- **Auswertungen**: Soll/Ist-Vergleich, Überstundenkonto, Urlaubskonto
- **Admin-Verwaltung**: Benutzerverwaltung, Monats-/Jahresberichte, Excel-Export
- **Compliance**: Ruhezeit-Überwachung (ArbZG), Feiertage nach Bundesland

### 1.2 Qualitätsziele

| Priorität | Qualitätsmerkmal | Motivation |
|-----------|------------------|------------|
| 1 | **Korrektheit** | Gehalts- und Urlaubsberechnungen müssen exakt sein |
| 2 | **Datenschutz** | Personaldaten erfordern Zugriffsschutz (DSGVO) |
| 3 | **Benutzerfreundlichkeit** | Praxispersonal ohne IT-Kenntnisse muss es bedienen können |
| 4 | **Verfügbarkeit** | Tägliche Nutzung erfordert hohe Uptime |
| 5 | **Wartbarkeit** | Codebase soll leicht erweiterbar sein |

### 1.3 Stakeholder

| Rolle | Interesse |
|-------|-----------|
| Praxisinhaber (Admin) | Übersicht über Arbeitszeiten, Compliance, Berichte |
| Mitarbeiterinnen | Einfache Zeiterfassung, Urlaubsverwaltung |
| Lohnbuchhaltung | Excel-Exporte für Gehaltsabrechnung |
| IT-Betreiber | Einfaches Deployment, Wartung |

---

## 2. Randbedingungen

### 2.1 Technische Randbedingungen

| Randbedingung | Begründung |
|---------------|------------|
| Docker-basiertes Deployment | Einfache Installation auf beliebiger Hardware |
| PostgreSQL als Datenbank | Zuverlässig, kostenfrei, bewährt |
| REST-API-Backend | Klare Trennung Frontend/Backend, API-Dokumentation |
| Single Page Application (React) | Responsive, mobile-ready |
| JWT Authentication | Stateless, skalierbar |

### 2.2 Organisatorische Randbedingungen

- Open Source (GitHub: https://github.com/phash/praxiszeit)
- Deployment typischerweise on-premise (lokaler Server in der Praxis)
- Datenhaltung lokal (kein Cloud-Zwang)

---

## 3. Kontextabgrenzung

### 3.1 Fachlicher Kontext

```
┌──────────────────────────────────────────────────────────┐
│                      PraxisZeit System                    │
│                                                           │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────┐  │
│  │  Mitarbeiter│    │     Admin    │    │  Lohnbuchh. │  │
│  │             │    │              │    │             │  │
│  │ - Zeiteintr │    │ - Benutzervw │    │ - Excel     │  │
│  │ - Abwesenh. │    │ - Berichte   │    │   Import    │  │
│  │ - Dashboard │    │ - Betriebsf. │    │             │  │
│  └──────┬──────┘    └──────┬───────┘    └─────────────┘  │
│         │                  │                              │
└─────────┼──────────────────┼──────────────────────────────┘
          │                  │
    ┌─────▼──────────────────▼─────┐
    │        Browser / PWA          │
    │    (React Frontend SPA)       │
    └───────────────┬──────────────┘
                    │ REST API / HTTPS
    ┌───────────────▼──────────────┐
    │       FastAPI Backend         │
    │  - JWT Auth                   │
    │  - Business Logic             │
    │  - workalendar (Feiertage)    │
    └───────────────┬──────────────┘
                    │
    ┌───────────────▼──────────────┐
    │        PostgreSQL DB          │
    └──────────────────────────────┘
```

### 3.2 Technischer Kontext

| Schnittstelle | Protokoll | Beschreibung |
|---------------|-----------|--------------|
| Browser → Backend | REST/JSON über HTTPS | API-Aufrufe |
| Backend → DB | psycopg2/SQLAlchemy | ORM-basiert |
| Backend → workalendar | Python-Bibliothek | Feiertagsberechnung |
| Admin → Excel | StreamingResponse | Excel-Export |

---

## 4. Lösungsstrategie

### Kernentscheidungen

1. **Backend-First**: FastAPI als modernes Python-Framework mit automatischer API-Dokumentation
2. **Layered Architecture**: Router → Service → Model (keine direkte DB-Zugriffe in Routers)
3. **Schema-Trennung**: Pydantic-Schemas separat von SQLAlchemy-Modellen (Request/Response getrennt)
4. **Historische Berechnungen**: Stundenänderungen werden tagesgenau berücksichtigt (`working_hours_changes`)
5. **PWA**: Offline-fähige Web-App ohne App-Store-Abhängigkeit

---

## 5. Bausteinsicht

### 5.1 Ebene 1 – Gesamtsystem

```
praxiszeit/
├── frontend/          # React SPA (TypeScript + Tailwind)
├── backend/           # FastAPI Python-Backend
├── docker-compose.yml # Orchestrierung aller Services
└── .env               # Konfiguration (Secrets)
```

### 5.2 Ebene 2 – Backend

```
backend/app/
├── main.py              # App-Einstiegspunkt + Lifespan-Events
├── config.py            # Settings via pydantic-settings
├── database.py          # SQLAlchemy Engine + Session
│
├── models/              # SQLAlchemy ORM-Modelle
│   ├── user.py          # User, UserRole
│   ├── time_entry.py    # TimeEntry
│   ├── absence.py       # Absence, AbsenceType
│   ├── public_holiday.py # PublicHoliday
│   ├── working_hours_change.py # Stundenhistorie
│   ├── company_closure.py # Betriebsferien
│   └── change_request.py  # Änderungsanträge
│
├── schemas/             # Pydantic Request/Response-Schemas
│   ├── user.py          # UserCreate, UserUpdate, UserResponse
│   ├── absence.py       # AbsenceCreate, AbsenceResponse
│   └── reports.py       # VacationAccount, EmployeeReport
│
├── routers/             # FastAPI-Endpoints
│   ├── auth.py          # Login, Refresh Token, Passwort
│   ├── admin.py         # Benutzerverwaltung
│   ├── time_entries.py  # CRUD Zeiteinträge
│   ├── absences.py      # CRUD Abwesenheiten
│   ├── dashboard.py     # Stats für Mitarbeiter
│   ├── holidays.py      # Feiertage
│   ├── reports.py       # Admin-Berichte + Export
│   ├── company_closures.py # Betriebsferien
│   └── change_requests.py  # Änderungsanträge
│
├── services/            # Business Logic
│   ├── auth_service.py  # Passwort-Hash, JWT
│   ├── calculation_service.py # Kern-Berechnungen
│   ├── export_service.py # Excel-Exporte
│   ├── holiday_service.py # Feiertag-Sync (workalendar)
│   └── rest_time_service.py # Ruhezeit-Prüfung
│
└── middleware/
    └── auth.py          # JWT-Validierung, get_current_user
```

### 5.3 Ebene 2 – Frontend

```
frontend/src/
├── App.tsx              # Router-Setup, Protected Routes
├── main.tsx             # React-Einstiegspunkt
│
├── pages/               # Seitenkomponenten
│   ├── Dashboard.tsx    # Mitarbeiter-Dashboard
│   ├── TimeTracking.tsx # Wochenansicht Zeiterfassung
│   ├── AbsenceCalendarPage.tsx # Kalender + Abwesenheiten
│   ├── Profile.tsx      # Profilverwaltung
│   └── admin/
│       ├── AdminDashboard.tsx # Team-Übersicht
│       ├── AdminAbsences.tsx  # Abwesenheiten + Betriebsferien
│       ├── Users.tsx    # Benutzerverwaltung
│       ├── Reports.tsx  # Berichte + Export + Ruhezeiten
│       └── AuditLog.tsx # Änderungsprotokoll
│
├── components/          # Wiederverwendbare UI-Komponenten
│   ├── Layout.tsx       # Navigation + Sidebar
│   ├── Button.tsx / Badge.tsx / FormInput.tsx
│   ├── ConfirmDialog.tsx # Bestätigungsdialog
│   ├── MonthSelector.tsx # Monatsnavigation
│   └── StampWidget.tsx  # Stempeluhr
│
├── contexts/
│   └── ToastContext.tsx  # Toast-Benachrichtigungen
│
├── hooks/
│   └── useConfirm.ts    # Dialog-State-Management
│
├── stores/
│   └── authStore.ts     # Zustand: Auth-State (JWT, User)
│
├── api/
│   └── client.ts        # Axios-Instanz mit Auth-Interceptor
│
└── constants/
    └── absenceTypes.ts  # Abwesenheitstypen + Labels
```

---

## 6. Laufzeitsicht

### 6.1 Login-Flow

```
Browser          Frontend          Backend          PostgreSQL
   │                │                 │                 │
   │── POST /login ─►│                 │                 │
   │                │─── POST /api/auth/login ──────────►│
   │                │                 │── SELECT user ──►│
   │                │                 │◄── user_row ─────│
   │                │                 │ hash_verify()    │
   │                │◄── JWT + User ──│                 │
   │◄── localStorage│                 │                 │
   │   (Token)      │                 │                 │
```

### 6.2 Zeiterfassung erstellen

```
Browser          Frontend          Backend          PostgreSQL
   │                │                 │                 │
   │── save ────────►│                 │                 │
   │                │── POST /api/time-entries ─────────►│
   │                │                 │── INSERT ───────►│
   │                │                 │◄── TimeEntry ────│
   │                │◄── 201 Created ─│                 │
   │◄── Toast: OK ──│                 │                 │
```

### 6.3 Urlaubsantrag mit Bereichsprüfung

```
Frontend                          Backend
   │                                 │
   │── POST /api/absences ──────────►│
   │   {type: vacation, end_date: X}  │
   │                                 │── Werktage berechnen
   │                                 │── Feiertage ausschließen
   │                                 │── Urlaubskonto prüfen
   │                                 │── INSERT für jeden Werktag
   │◄── [AbsenceResponse, ...] ──────│
```

---

## 7. Verteilungssicht

### 7.1 Deployment-Architektur

```
┌─────────────────────────── Docker Host ──────────────────────────┐
│                                                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   frontend      │  │    backend      │  │      db         │  │
│  │   (Nginx)       │  │   (Uvicorn)     │  │  (PostgreSQL)   │  │
│  │   Port 80       │  │   Port 8000     │  │   Port 5432     │  │
│  │                 │  │                 │  │                 │  │
│  │  React SPA      │  │  FastAPI App    │  │  praxiszeit     │  │
│  │  Static Files   │  │  + Workers      │  │  Database       │  │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  │
│           │                    │                     │            │
│  ┌────────▼────────────────────▼─────────────────────▼────────┐  │
│  │                    Docker Network (intern)                   │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  Volumes: db_data (persistent PostgreSQL-Daten)                    │
└────────────────────────────────────────────────────────────────────┘
         │
    Port 80/443
         │
    ┌────▼────────────┐
    │  Nginx Reverse  │
    │  Proxy (opt.)   │
    │  (HTTPS/TLS)    │
    └─────────────────┘
         │
    Internet/LAN
```

### 7.2 Konfiguration (Umgebungsvariablen)

| Variable | Beschreibung | Standardwert |
|----------|--------------|--------------|
| `DATABASE_URL` | PostgreSQL Connection String | – |
| `SECRET_KEY` | JWT-Signing-Key | – |
| `CORS_ORIGINS` | Erlaubte Origins | `*` |
| `HOLIDAY_STATE` | Bundesland für Feiertage | `Bayern` |
| `ADMIN_USERNAME` | Initial-Admin Benutzername | `admin` |
| `ADMIN_EMAIL` | Initial-Admin Email | – |
| `ADMIN_PASSWORD` | Initial-Admin Passwort | – |

---

## 8. Querschnittskonzepte

### 8.1 Authentifizierung & Autorisierung

- **JWT Bearer Tokens** (HS256, 30 Min. Gültigkeit)
- **Refresh Tokens** (7 Tage)
- **Role-Based Access Control**: `admin` vs. `employee`
- Middleware: `get_current_user()`, `require_admin()` als FastAPI Dependencies

```python
# Pattern für geschützte Endpoints
@router.get("/admin/users")
def list_users(current_user: User = Depends(require_admin)):
    ...
```

### 8.2 Datenbankmigrationen

- **Alembic** für Schema-Migrationen
- Automatische Ausführung beim App-Start (`alembic upgrade head`)
- Migration-Files in `backend/alembic/versions/` (nummeriert 001–012)
- Konvention: `YYYY_MM_DD_HHMM-NNN_beschreibung.py`

### 8.3 Fehlerbehandlung

**Backend:**
```python
# HTTP Exceptions mit deutschsprachigen Meldungen
raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
```

**Frontend:**
```tsx
// Toast-Benachrichtigungen statt native alert()
toast.error(error.response?.data?.detail || 'Fehler beim Speichern');
```

### 8.4 Business-Logic-Muster

**Historische Stundenberechnung** (kritisch für korrekte Berechnungen):
```python
# RICHTIG: Tag-für-Tag mit historischen Stunden
for day in date_range:
    hours = get_weekly_hours_for_date(db, user, day)  # berücksichtigt Änderungshistorie
    target = hours / 5  # Soll-Stunden pro Tag

# FALSCH: Aktuelle Stunden für gesamten Zeitraum verwenden
target = user.weekly_hours / 5
```

**Datumsbereichs-Abwesenheiten:**
- Jeder Werktag (Mo-Fr) wird als separater DB-Eintrag gespeichert
- Wochenenden und Feiertage werden automatisch ausgeschlossen
- `end_date` wird in jedem Eintrag gespeichert (für UI-Darstellung)

### 8.5 Responsive Design

- **Desktop**: Tabellen mit allen Details
- **Mobile** (< 768px): Card-Layouts, Hamburger-Menu, kompakte Darstellung
- **PWA**: Installierbar, Service Worker, Offline-Cache für statische Assets

### 8.6 Feiertage

- **workalendar**-Bibliothek für alle 16 deutschen Bundesländer
- Konfigurierbar via `HOLIDAY_STATE` Umgebungsvariable
- Automatische Synchronisation beim App-Start (aktuelles + Folgejahr)
- Deutsche Übersetzung der Feiertagsnamen (Translation Dictionary)

---

## 9. Architekturentscheidungen

### ADR-001: FastAPI statt Django/Flask
- **Status**: Entschieden (2026-02)
- **Kontext**: Python-Backend für REST-API benötigt
- **Entscheidung**: FastAPI
- **Begründung**: Automatische API-Dokumentation (Swagger), native async-Unterstützung, Pydantic-Integration, modernes Python
- **Konsequenzen**: Steile Lernkurve bei Dependency Injection, aber sehr saubere Architektur

### ADR-002: Zustand statt Redux
- **Status**: Entschieden (2026-02)
- **Kontext**: State Management im React-Frontend
- **Entscheidung**: Zustand (nur für Auth-State)
- **Begründung**: Minimaler Boilerplate, ausreichend für Auth-State; Server-State wird per-Page gefetcht
- **Konsequenzen**: Kein globaler Cache für Server-Daten (bewusste Entscheidung für Einfachheit)

### ADR-003: Username statt Email für Login
- **Status**: Entschieden (2026-02)
- **Kontext**: `EmailStr` in Pydantic lehnt `.local`-TLDs ab
- **Entscheidung**: Username-basierter Login, Email optional
- **Begründung**: Praxisinterne Systeme nutzen oft keine echten E-Mail-Adressen; Flexibilität
- **Konsequenzen**: Migration aller Benutzer auf Username nötig (Migration 010)

### ADR-004: Separate DB-Einträge für Abwesenheits-Zeiträume
- **Status**: Entschieden (2026-02)
- **Kontext**: Urlaubsbuchungen für mehrere Tage
- **Entscheidung**: Ein DB-Eintrag pro Arbeitstag (nicht Range-Eintrag)
- **Begründung**: Einfachere Abfragen, Feiertage/Wochenenden automatisch ausgeschlossen, historische Stundenberechnung per Tag
- **Konsequenzen**: Mehr DB-Rows bei langen Urlauben, aber `end_date` gespeichert für UI-Darstellung

---

## 10. Qualitätsszenarien

### 10.1 Korrektheit

| Szenario | Stimulus | Reaktion |
|----------|----------|----------|
| Stundenänderung rückwirkend | Admin ändert Teilzeit ab 01.03. | Alle Monate ab März berechnen Soll mit neuen Stunden |
| Feiertag in Urlaubszeitraum | Urlaub über Ostern | Karfreitag/Ostermontag nicht als Urlaubstag gezählt |
| Krankmeldung im Urlaub | MA krank während Urlaub | Dialog zum Rückerstatten der Urlaubstage |

### 10.2 Sicherheit

| Szenario | Stimulus | Reaktion |
|----------|----------|----------|
| Unauthentifizierter API-Zugriff | GET /api/time-entries ohne Token | 401 Unauthorized |
| Employee greift auf Admin-Endpoint zu | GET /api/admin/users mit Employee-Token | 403 Forbidden |
| Token abgelaufen | API-Call mit 30-min-altem Token | 401, Frontend leitet zu /login |

### 10.3 Performance

| Szenario | Last | Ziel |
|----------|------|------|
| Dashboard laden | 1 Concurrent User | < 500ms |
| Excel-Export (Jahresreport detailliert) | 10 Mitarbeiter | < 10s |
| Feiertagssync beim Start | 2 Jahre | < 2s |

---

## 11. Risiken und technische Schulden

| Risiko | Schwere | Wahrscheinlichkeit | Maßnahme |
|--------|---------|-------------------|----------|
| N+1 Queries bei Admin-Dashboard | Mittel | Hoch | Eager Loading mit joinedload() |
| Keine E2E-Tests | Hoch | – | Playwright/Cypress Tests planen |
| CORS auf `*` in Produktion | Hoch | Mittel | `CORS_ORIGINS` korrekt setzen |
| Keine Passwort-Reset-Funktion | Niedrig | – | Email-basierter Reset als Future Feature |
| Keine Rate-Limiting auf Login | Mittel | Niedrig | slowapi bereits im Stack |

---

## 12. Glossar

| Begriff | Definition |
|---------|------------|
| **Soll-Stunden** | Vertraglich vereinbarte Wochenstunden / 5 Arbeitstage |
| **Ist-Stunden** | Tatsächlich erfasste Arbeitszeit (End - Start - Pause) |
| **Überstunden** | Ist - Soll (positiv = Mehrarbeit, negativ = Minusstunden) |
| **Urlaubskonto** | Budget (Urlaubstage × Tagessoll) minus genutzter Urlaub |
| **Betriebsferien** | Admin-definierte Schließungszeit = Urlaub für alle MA |
| **Ruhezeit** | Mindestruhezeit zwischen zwei Schichten (§5 ArbZG: 11h) |
| **Workalendar** | Python-Bibliothek für Feiertagsberechnungen |
| **PWA** | Progressive Web App – im Browser installierbar |
| **JWT** | JSON Web Token für stateless Authentication |
| **ADR** | Architecture Decision Record |

---

*Dieses Dokument folgt dem arc42-Template v8.2 (https://arc42.org)*
