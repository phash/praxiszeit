# CLAUDE.md – PraxisZeit

**Repo:** https://github.com/phash/praxiszeit
**Stack:** React 18 + TypeScript + Tailwind / FastAPI (Python 3.12) + PostgreSQL 16 / Docker Compose

---

## Schnellreferenz

### Start
```bash
docker compose up -d          # Frontend :80, API-Docs :8000/docs
docker compose down
```

### Tests
```bash
cd e2e && npx playwright test                                    # E2E (71 Tests, ~20 Min)
docker compose exec backend pytest tests/ -v                     # Backend Unit (127 Tests)
docker compose exec backend pytest tests/test_tenant_rls.py -v   # RLS Integration (13 Tests)
```
Nach nginx.conf / Frontend-Änderungen: `docker compose build frontend && docker compose up -d frontend`

### Kritische Regeln
- `get_weekly_hours_for_date()` **immer** pro Tag – nie `user.weekly_hours` direkt
- Migrationen auf Host erstellen + committen **vor** Container-Rebuild
- Pydantic Response-Schemas: `float` statt `Decimal`
- `docs/generated/` ist gitignored
- nginx SPA vs. Static-Dir: `location = /route` VOR `location /` einfügen
- Stunden-Anzeige: `formatHoursHM()` aus `utils/errorMessage.ts` (H:MM, Overflow-safe)
- Cross-Page Refresh nach Stempeln: `uiStore.notifyStampChange()` → `stampVersion` Effect

### Multi-Tenant (Branch: feat/multi-tenant-phase-1-3)
- **Jede neue Tabelle** braucht `tenant_id` FK + RLS-Policy + Eintrag in Migration
- **Neue Endpoints:** `set_tenant_context(db, tid)` oder `set_superadmin_context(db)` aufrufen
- **Neue Sessions** (`SessionLocal()` direkt): RLS-Kontext setzen, sonst 0 Rows!
- **DB-User:** App = `praxiszeit_app` (RLS enforced), Migrations = `praxiszeit` (Superuser)
- **JWT:** `tid` Claim enthält tenant_id, Middleware validiert gegen DB
- Default-Tenant UUID: `00000000-0000-0000-0000-000000000001`
- `set_tenant_context()` nutzt Event-Listener → überlebt `db.commit()`

### Standard-Benutzer
- Admin: `admin` / `Admin2025!`
- Mitarbeiter: `manuel@klotz-roedig.de`

### Doku-Struktur
```
docs/
├── ARC42.md, INSTALLATION.md, SECURITY.md
├── handbuch/          # Handbücher + Screenshots
├── plans/             # Alle Implementation Plans
├── specs/             # Alle Specs + Design-Docs
│   ├── arbzg/         # ArbZG-Compliance
│   ├── dsgvo/         # DSGVO-Compliance
│   ├── features/      # Feature-Specs
│   └── security/      # Security-Specs
```

---
*Entwickelt mit Claude Sonnet 4.5, Sonnet 4.6 & Opus 4.6*
