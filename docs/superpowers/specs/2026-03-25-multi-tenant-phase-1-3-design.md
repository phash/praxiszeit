# Multi-Tenant Phase 1-3: Tenants-Tabelle, Middleware, RLS

**Issue:** #73
**Scope:** Phase 1 (DB), Phase 2 (Middleware), Phase 3 (RLS)
**Datum:** 2026-03-25

---

## Zusammenfassung

PraxisZeit wird von Single-Tenant zu Multi-Tenant umgebaut. Eine Codebasis, die beides kann — gesteuert über `tenants.mode` (`single`/`multi`). Im Single-Modus kann kein neuer Tenant angelegt werden.

### Entscheidungen

| Frage | Entscheidung |
|-------|-------------|
| Scope | Phase 1-3 (DB + Middleware + RLS). Signup, SSO, Billing später |
| Username-Uniqueness | Tenant-scoped (`tenant_id + username`) |
| SystemSettings | Eine Tabelle, `tenant_id` nullable (NULL = global) |
| PublicHolidays | Tenant-scoped (eigene Feiertage pro Tenant) |
| Superadmin | User ohne `tenant_id` (NULL), kein neues Rollen-Feld |
| URL-Struktur | Keine Änderung — Tenant kommt aus JWT, nicht aus URL |
| Default-Tenant | Name "Default", vom Admin im UI änderbar |
| Migrations-Ansatz | Big-Bang — eine atomare Alembic-Migration (027) |
| Deployment | Prod-Instanz (Klotz-Roedig) bleibt Einzel-Hosting. Neuer VPS für Multi-Tenant SaaS (MRD) |

---

## 1. Tenants-Tabelle

```python
class Tenant(Base):
    __tablename__ = 'tenants'
    id         = Column(UUID, primary_key=True, default=uuid4)
    name       = Column(String(255), nullable=False)       # "Praxis Dr. Mueller"
    slug       = Column(String(100), unique=True)          # für spätere URL-Nutzung
    is_active  = Column(Boolean, default=True)
    mode       = Column(String(20), default='multi')       # 'single' | 'multi'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

Billing-Felder (`plan`, `stripe_customer_id`, `max_employees`, `trial_ends_at`) kommen in späteren Phasen.

---

## 2. tenant_id auf alle Tabellen

### Direkt tenant-scoped (eigene tenant_id):
- `users` — **nullable** (NULL = Superadmin)
- `public_holidays` — NOT NULL
- `company_closures` — NOT NULL
- `system_settings` — **nullable** (NULL = globale Settings)
- `error_logs` — NOT NULL

### Indirekt über User (haben user_id, bekommen trotzdem eigene tenant_id für RLS):
- `time_entries` — NOT NULL
- `absences` — NOT NULL
- `vacation_requests` — NOT NULL
- `change_requests` — NOT NULL
- `time_entry_audit_logs` — NOT NULL
- `working_hours_changes` — NOT NULL
- `year_carryovers` — NOT NULL

### Geänderte Unique Constraints

| Tabelle | Alt | Neu |
|---------|-----|-----|
| `users` | `UNIQUE(username)` | `UNIQUE(tenant_id, username)` |
| `users` | `UNIQUE(email)` (nullable) | `UNIQUE(tenant_id, email)` |
| `time_entries` | `UNIQUE(user_id, date, start_time)` | `UNIQUE(tenant_id, user_id, date, start_time)` |
| `absences` | `UNIQUE(user_id, date, type)` | `UNIQUE(tenant_id, user_id, date, type)` |

---

## 3. Migration 027 — Ablauf

Eine atomare Alembic-Migration:

```
1. CREATE TABLE tenants (...)
2. INSERT Default-Tenant ("Default", slug="default", mode="single")
3. Für jede der 12 Tabellen:
   a. ADD COLUMN tenant_id UUID (nullable)
   b. UPDATE SET tenant_id = <default_tenant_id>
   c. ALTER COLUMN SET NOT NULL (außer users + system_settings)
   d. ADD FOREIGN KEY → tenants(id)
4. DROP alte Unique Constraints
5. CREATE neue Unique Constraints (mit tenant_id)
6. Vollständiger Downgrade implementiert
```

### Garantien:
- Alle bestehenden Rows bekommen den Default-Tenant
- Kein User, Passwort, Rolle ändert sich
- Login funktioniert identisch weiter
- Row-Counts vor/nach Migration identisch
- Downgrade stellt Original-Schema wieder her

---

## 4. JWT-Erweiterung

### Payload
```
Bisher:  { sub, role, type, tv, exp }
Neu:     { sub, role, type, tv, tid, exp }
```

- `tid` = `tenant_id` des Users (UUID string)
- Superadmin (tenant_id = NULL): `tid` fehlt im Token

### Abwärtskompatibilität
Alte Token ohne `tid` funktionieren weiter. Middleware liest `tenant_id` als Fallback vom User-Objekt. Beim nächsten Refresh bekommt der User ein Token mit `tid`.

---

## 5. Tenant-Middleware

Erweiterung von `get_current_user()`:

```
1. JWT dekodieren (wie bisher)
2. User laden (wie bisher)
3. tid aus Token lesen (Fallback: user.tenant_id)
4. Wenn tid vorhanden:
   → SET LOCAL app.tenant_id = '<tid>' auf DB-Session
   → request.state.tenant_id = tid
5. Wenn tid fehlt (Superadmin):
   → RLS nicht setzen, Zugriff auf alles
```

---

## 6. PostgreSQL Row-Level Security

### Standard-Policy (10 Tabellen)
```sql
ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <table> FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON <table>
  USING (
    current_setting('app.tenant_id', true) IS NULL
    OR tenant_id = current_setting('app.tenant_id')::uuid
  );
```

- `current_setting('app.tenant_id', true)` gibt NULL zurück statt Fehler
- Superadmin (kein `app.tenant_id` gesetzt) → sieht alles
- Tenant-User → sieht nur eigene Daten

### Sonderfall: system_settings + users (nullable tenant_id)
```sql
CREATE POLICY tenant_isolation ON system_settings
  USING (
    current_setting('app.tenant_id', true) IS NULL
    OR tenant_id = current_setting('app.tenant_id')::uuid
    OR tenant_id IS NULL
  );
```

Tenant-User sehen: eigene Settings + globale Settings (tenant_id IS NULL).

### DB-User-Trennung
- App-DB-User: kein Superuser → RLS greift
- Migrations-DB-User: Superuser → kann Schema ändern ohne RLS-Einschränkung

---

## 7. Testplan

### 7.1 Migrations-Tests (gegen Prod-DB-Kopie)
- Migration 027 upgrade läuft fehlerfrei
- Alle Rows haben `tenant_id` = Default-Tenant
- Unique Constraints greifen korrekt
- Downgrade funktioniert — Schema danach identisch
- Row-Counts vor/nach identisch

### 7.2 RLS-Tests (pytest)
- Tenant A sieht nur eigene Daten (alle 12 Tabellen)
- Tenant A kann Tenant B nicht lesen/schreiben/updaten/löschen
- Superadmin sieht alle Tenants
- `system_settings` mit tenant_id = NULL sind für alle sichtbar
- INSERT ohne korrektes tenant_id wird blockiert

### 7.3 Auth/JWT-Tests
- Login liefert Token mit `tid`
- Superadmin-Token hat kein `tid`
- Token-Refresh liefert `tid` (auch für alte Token ohne `tid`)
- `get_current_user` setzt `app.tenant_id` auf DB-Session

### 7.4 Regressions-Tests
- Bestehende 112 E2E-Tests grün mit Default-Tenant
- Login/Logout unverändert
- Admin sieht nur User seines Tenants
- Employee sieht nur eigene Daten

### 7.5 Multi-Tenant-Integrationstests
- Zwei Test-Tenants mit je Users + Daten
- Tenant-Isolation auf allen 12 Tabellen verifiziert

---

## 8. Betroffene Dateien

### Backend — Models
- `backend/app/models/` — neues `tenant.py`, alle bestehenden Models bekommen `tenant_id`
- `backend/app/models/__init__.py` — Tenant exportieren

### Backend — Auth
- `backend/app/services/auth_service.py` — `tid` in JWT-Payload
- `backend/app/middleware/auth.py` — `SET LOCAL app.tenant_id`, Fallback-Logik

### Backend — Database
- `backend/app/database.py` — ggf. zweiter DB-User für App vs. Migration
- `backend/alembic/versions/027_*.py` — Big-Bang-Migration

### Backend — Routers
- Alle Router die `get_current_user` nutzen: keine Änderung nötig (RLS filtert automatisch)
- Admin-Router: Tenant-Kontext kommt über Middleware, keine Query-Änderungen

### Frontend
- Keine Änderungen in Phase 1-3 (URL bleibt gleich, JWT-Handling transparent)

### Docker
- Ggf. separater DB-User in docker-compose.yml für App vs. Migrations
