# PraxisZeit - Zeiterfassungssystem

Webbasiertes Zeiterfassungssystem für eine Arztpraxis in Bayern.
Installierbar als **Progressive Web App (PWA)** auf Smartphone und Desktop.

## Features

### Für Mitarbeiter
- ✅ **Stempeluhr** - Ein-/Ausstempeln direkt auf dem Dashboard
- ✅ **Zeiterfassung** (von–bis mit Pausen)
- ✅ **Dashboard** mit Soll/Ist-Vergleich und Überstundenkonto
- ✅ **Urlaubsverwaltung** (stundenbasiert mit Restanzeige)
- ✅ **Abwesenheiten** (Urlaub, Krankheit, Fortbildung, Sonstiges)
- ✅ **Zeitraum-Erfassung** (mehrere Tage auf einmal)
- ✅ **Profilseite** (Passwort ändern, persönliche Daten)
- ✅ **Änderungsanträge** für vergangene Tage

### Für Admins
- ✅ **Benutzerverwaltung** mit Rollenverwaltung
- ✅ **Arbeitszeiten-Historie** (Stundenänderungen nachverfolgen)
- ✅ **Urlaubsübersicht** (Budget, Verbrauch, Resturlaub pro MA)
- ✅ **Kalenderfarben** für Abwesenheitskalender
- ✅ **Admin-Dashboard** mit Team-Übersicht
- ✅ **Berichte & Export**:
  - Monatsreport (detailliert mit täglichen Einträgen)
  - Jahresreport Classic (kompakte 12-Monats-Übersicht)
  - Jahresreport Detailliert (365 Tage pro MA)
- ✅ **Abwesenheitskalender** für das ganze Team
- ✅ **Änderungsanträge** genehmigen/ablehnen

### Weitere Features
- 📱 **PWA** - Installierbar als App auf Smartphone und Desktop
- 🗓️ **Bayerischer Feiertagskalender** (automatisch berücksichtigt)
- 📅 **Wochenenden** automatisch ausschließen bei Zeiträumen
- 📊 **Historische Stundenänderungen** werden korrekt berechnet
- 🎨 **Responsive Design** (Desktop & Mobile)
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

- **users** - Benutzer mit Rollen, Wochenstunden, Urlaubsanspruch, Kalenderfarbe
- **working_hours_changes** - Historie von Stundenänderungen
- **time_entries** - Zeiteinträge (Start, Ende nullable für Stempeluhr, Pausen)
- **absences** - Abwesenheiten mit Typ und optional Zeitraum
- **public_holidays** - Bayerische Feiertage
- **change_requests** - Änderungsanträge für vergangene Einträge
- **time_entry_audit_logs** - Audit-Logs für Zeiteinträge

### Migrationen

Die Datenbank wird beim Start automatisch migriert. Manuelle Migration:

```bash
docker-compose exec backend alembic upgrade head
```

Neue Migration erstellen:

```bash
docker-compose exec backend alembic revision --autogenerate -m "description"
```

**Aktuelle Migrationen:**
- `001` - Initial Schema (User, TimeEntry, Absence, PublicHoliday)
- `002` - Add track_hours field
- `003` - Add end_date to absences (Zeiträume)
- `004` - Add calendar_color to users
- `005` - Add working_hours_changes table
- `006` - Add work_days_per_week
- `007` - Add change_requests
- `008` - Add time_entry_audit_logs
- `009` - Make end_time nullable (Stempeluhr)

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

**Dashboard:**
- `GET /api/dashboard` - Dashboard-Daten
- `GET /api/dashboard/overtime` - Überstundenkonto mit Historie
- `GET /api/dashboard/vacation` - Urlaubskonto

## Deployment

### Produktions-Deployment

1. Server mit Docker & Docker Compose vorbereiten
2. Repository klonen
3. `.env` mit Produktions-Credentials erstellen
4. SSL/TLS mit nginx reverse proxy einrichten
5. Container starten: `docker-compose up -d`

### Backup

**Datenbank-Backup:**
```bash
docker-compose exec db pg_dump -U praxiszeit praxiszeit > backup.sql
```

**Datenbank-Restore:**
```bash
docker-compose exec -T db psql -U praxiszeit praxiszeit < backup.sql
```

## Support & Dokumentation

- **CLAUDE.md** - Umfangreiche Projekt-Dokumentation
- **API Docs** - http://localhost:8000/docs
- **GitHub Issues** - https://github.com/phash/praxiszeit/issues

## Lizenz

Proprietär - Alle Rechte vorbehalten
