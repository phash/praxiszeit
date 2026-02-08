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
- 🎨 **Responsive Design**: Funktioniert auf Desktop und Mobile

## 🏗️ Projekt-Struktur

```
praxiszeit/
├── backend/
│   ├── app/
│   │   ├── models/          # SQLAlchemy Models (User, TimeEntry, Absence, etc.)
│   │   ├── routers/         # FastAPI Endpoints
│   │   ├── schemas/         # Pydantic Schemas
│   │   ├── services/        # Business Logic
│   │   └── middleware/      # Auth Middleware
│   ├── alembic/
│   │   └── versions/        # Datenbankmigrationen
│   └── tests/               # Pytest Tests
├── frontend/
│   └── src/
│       ├── pages/           # React Pages
│       ├── components/      # React Components
│       └── stores/          # Zustand State Management
└── docker-compose.yml       # Docker Setup

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
```

### Migration erstellen
```bash
docker-compose exec backend alembic revision --autogenerate -m "description"
```

### Migration ausführen
```bash
docker-compose exec backend alembic upgrade head
```

## 🗄️ Datenbank

**PostgreSQL 16** mit folgenden Haupttabellen:
- `users` - Benutzer mit Rollen, Wochenstunden, Urlaubsanspruch, Kalenderfarbe
- `working_hours_changes` - Historie von Arbeitszeitenänderungen mit Datum und Notiz
- `time_entries` - Zeiteinträge (Start, Ende, Pausen)
- `absences` - Abwesenheiten mit Typ und optional Zeitraum (end_date)
- `public_holidays` - Feiertage nach Bundesland

**Migrationen:**
- 001: Initial Schema (User, TimeEntry, Absence, PublicHoliday)
- 002: Add track_hours field (Stundenzählung deaktivierbar)
- 003: Add end_date to absences (Zeiträume)
- 004: Add calendar_color to users (Farbcodierung im Kalender)
- 005: Add working_hours_changes table (Arbeitszeiten-Historie)

## 👤 Standard-Benutzer

Nach dem ersten Start existieren folgende Benutzer:
- **Admin**: admin@praxis.de
- **Test-Admin** (für Screenshots): admin@example.com / admin123
- **Mitarbeiter**: manuel@example.de

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

## 🎯 API Endpoints

### Authentication
- POST `/api/auth/login` - Login mit Email/Passwort
- GET `/api/auth/me` - Aktueller User
- PUT `/api/auth/password` - Passwort ändern

### Time Entries
- GET `/api/time-entries` - Liste (mit Filter)
- POST `/api/time-entries` - Neuer Eintrag
- PUT `/api/time-entries/{id}` - Bearbeiten
- DELETE `/api/time-entries/{id}` - Löschen

### Absences
- GET `/api/absences` - Liste
- POST `/api/absences` - Neue Abwesenheit (auch Zeiträume)
- DELETE `/api/absences/{id}` - Löschen
- GET `/api/absences/calendar` - Kalender-Ansicht (alle Mitarbeiter)

### Admin
- GET `/api/admin/users` - Alle Benutzer
- POST `/api/admin/users` - User anlegen
- PUT `/api/admin/users/{id}` - User bearbeiten
- GET `/api/admin/dashboard` - Dashboard Daten
- GET `/api/admin/reports` - Monatsberichte

### Dashboard
- GET `/api/dashboard` - Dashboard Daten für aktuellen User

## 🔐 Sicherheit

- Passwörter werden mit bcrypt gehasht
- JWT Tokens mit HS256 Signatur
- Token-basierte API Authentication
- Role-based Access Control (Admin/Employee)
- Input Validation mit Pydantic

## 📚 Dokumentation

- **API Dokumentation**: http://localhost:8000/docs (Swagger UI)
- **PDF-Handbuch**: `screenshots/PraxisZeit-Handbuch.pdf`
- **Screenshots**: `screenshots/` Ordner mit allen Features

## 🐛 Bekannte Issues / Lessons Learned

1. **Decimal vs Float**: Pydantic serialisiert Decimal als String. Für Frontend besser float verwenden.
   - Bei Excel-Export: Decimal/float-Mixing vermeiden (TypeError)
   - Lösung: Konsistent float() verwenden oder beide Seiten zu Decimal konvertieren

2. **Email Validation**: `.local` TLD ist reserviert und schlägt bei Pydantic EmailStr fehl.

3. **Date Range Logic**: Bei Zeiträumen nur Werktage (Mo-Fr) erstellen und Feiertage ausschließen.

4. **Login für Screenshots**: Test-Admin muss existieren für automatische Screenshots.

5. **Historische Berechnungen**:
   - Bei Stundenänderungen Tag-für-Tag iterieren, nicht Monatsmittelwerte
   - `get_weekly_hours_for_date()` für jedes Datum aufrufen
   - Sortierung nach `effective_from DESC` wichtig für korrekte Historie

6. **Migration-Handling in Docker**:
   - Migrationen auf Host erstellen, BEVOR Container rebuildet werden
   - `docker-compose exec backend alembic revision --autogenerate`
   - Migration-Files müssen auf Host existieren, sonst gehen sie beim Rebuild verloren

7. **SQLAlchemy Session Management**:
   - Objekte aus einer Session nicht in anderer Session verwenden
   - Bei Batch-Operations: IDs zwischenspeichern, dann in neuer Session neu laden

8. **Excel Export Performance**:
   - Classic Format (12 Monate): ~17KB, schnell
   - Detailliert (365 Tage): ~108KB, dauert länger
   - Bei großen Exports Benutzer informieren (Loading-State)

## 🚀 Deployment

Das Projekt ist container-basiert und kann einfach deployed werden:

```bash
# Auf Server
git clone https://github.com/phash/praxiszeit
cd praxiszeit
docker-compose up -d
```

Wichtig:
- `.env` Datei mit Produktions-Credentials erstellen
- `SECRET_KEY` in Production ändern
- PostgreSQL Daten in Volume persistieren (bereits konfiguriert)

## 📝 Nächste Schritte / TODOs

- [ ] Passwort-Reset-Funktion per Email
- [ ] Benachrichtigungen bei Urlaubsantrag
- [ ] PDF-Export für Monatsberichte
- [ ] Mobile App (React Native)
- [ ] 2-Faktor-Authentifizierung
- [ ] Audit Log für Admin-Aktionen

## 🎨 Design-System

**Farben:**
- Primary: `#3b82f6` (blue-500)
- Hover: `#2563eb` (blue-600)
- Urlaub: blue
- Krank: red
- Fortbildung: orange
- Sonstiges: gray

**Komponenten:**
- Tailwind CSS Utility Classes
- Lucide React Icons
- Responsive Grid Layout

---

**Entwickelt mit Claude Sonnet 4.5**
