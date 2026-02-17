# Spec: Authentifizierung & Benutzerverwaltung

**Status:** Done
**Erstellt:** 2026-02-01
**Zuletzt aktualisiert:** 2026-02-17
**Zugehörige Issues:** #9

---

## Überblick

Benutzerverwaltung mit username-basierter Authentifizierung (JWT), rollenbasierter Zugriffskontrolle (Admin/Employee) und Admin-seitigem Passwort-Management. Email ist optional und wird nicht für Login benötigt.

---

## Requirements

### Funktionale Anforderungen

Als **Mitarbeiter** möchte ich mich mit Benutzername und Passwort anmelden, damit ich auf meine Zeiterfassungsdaten zugreifen kann.

- [x] **REQ-1**: Login mit Benutzername (nicht Email) + Passwort
- [x] **REQ-2**: JWT-Token wird nach Login zurückgegeben (Gültigkeit: 60 Minuten)
- [x] **REQ-3**: Alle API-Endpunkte außer `/api/auth/login` und `/api/health` erfordern gültigen Bearer-Token
- [x] **REQ-4**: Admin kann neue Benutzer anlegen (Vorname, Nachname, Username, Passwort, Wochenstunden, Urlaubstage)
- [x] **REQ-5**: Admin setzt Passwort direkt beim Anlegen (kein Temp-Passwort)
- [x] **REQ-6**: Mitarbeiter können eigenes Passwort ändern
- [x] **REQ-7**: Admin kann Benutzer deaktivieren (soft-delete via `is_active=False`)
- [x] **REQ-8**: Admin kann Arbeitszeiten-Änderungen mit Wirkungsdatum erfassen
- [x] **REQ-9**: `track_hours=False` deaktiviert Arbeitszeiterfassung für einen Benutzer (Soll = 0)

### Nicht-funktionale Anforderungen

- [x] Passwörter bcrypt-gehasht (passlib)
- [x] JWT mit HS256, SECRET_KEY aus Umgebungsvariable
- [x] Role-based Access: `admin` vs `employee`
- [x] Admin-User wird beim ersten Start automatisch erstellt (via `ADMIN_USERNAME`, `ADMIN_PASSWORD`)

### Out of Scope

- Passwort-Reset per E-Mail
- 2-Faktor-Authentifizierung
- OAuth/Social Login

---

## Design

### Datenbank

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,          -- optional
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'employee',  -- 'admin' | 'employee'
    weekly_hours DECIMAL(4,2) NOT NULL DEFAULT 40,
    work_days_per_week INTEGER NOT NULL DEFAULT 5,
    vacation_days INTEGER NOT NULL DEFAULT 30,
    vacation_carryover_deadline DATE,   -- optional, default: 31.03. des Folgejahres
    track_hours BOOLEAN DEFAULT TRUE,
    calendar_color VARCHAR(7) DEFAULT '#3B82F6',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE working_hours_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    weekly_hours DECIMAL(4,2) NOT NULL,
    effective_from DATE NOT NULL,
    note VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Backend (FastAPI)

| Methode | Pfad | Auth | Beschreibung |
|---------|------|------|-------------|
| `POST` | `/api/auth/login` | – | Login → JWT Token |
| `GET` | `/api/auth/me` | Employee | Eigenes Profil |
| `PUT` | `/api/auth/password` | Employee | Passwort ändern |
| `GET` | `/api/admin/users` | Admin | Alle Benutzer |
| `POST` | `/api/admin/users` | Admin | Benutzer anlegen |
| `PUT` | `/api/admin/users/{id}` | Admin | Benutzer bearbeiten |
| `GET` | `/api/admin/users/{id}/working-hours-changes` | Admin | Stundenhistorie |
| `POST` | `/api/admin/users/{id}/working-hours-changes` | Admin | Neue Stundenänderung |

**Betroffene Dateien:**
- `backend/app/models/user.py`
- `backend/app/schemas/user.py`
- `backend/app/routers/auth.py`
- `backend/app/routers/admin.py`
- `backend/app/services/auth_service.py`
- `backend/app/middleware/auth.py`

---

## Tasks

- [x] **T-1**: Initial Schema Migration (001)
- [x] **T-2**: Username + optionale Email Migration (010)
- [x] **T-3**: vacation_carryover_deadline Migration (011)
- [x] **T-4**: JWT Auth Service
- [x] **T-5**: Auth Router (login, me, password)
- [x] **T-6**: Admin Users Router
- [x] **T-7**: Frontend Login-Seite
- [x] **T-8**: Zustand Auth Store
- [x] **T-9**: Admin Benutzerverwaltung
