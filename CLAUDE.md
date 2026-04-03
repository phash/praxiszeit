# CLAUDE.md – PraxisZeit

**Repo:** https://github.com/phash/praxiszeit
**Stack:** React 18 + TypeScript + Tailwind / FastAPI (Python 3.12) + PostgreSQL 16 / Docker Compose

---

## Schnellreferenz

### Dev-Start
```bash
docker compose up -d          # Frontend :80, API-Docs :8000/docs
docker compose down
```

### Prod-Deployment
```bash
ssh manuel@192.168.178.44 "cd /opt/praxiszeit/praxiszeit && sudo ./deploy.sh"
```
→ Details: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

### Tests
```bash
cd e2e && npx playwright test                                    # E2E (114 Tests)
docker compose exec backend pytest tests/ -v                     # Backend Unit (343 Tests)
docker compose exec backend pytest tests/test_tenant_rls.py -v   # RLS Integration (13 Tests)
```
Nach nginx.conf / Frontend-Änderungen: `docker compose build frontend && docker compose up -d frontend`

### Kritische Regeln
- `get_weekly_hours_for_date()` **immer** pro Tag – nie `user.weekly_hours` direkt
- Migrationen auf Host erstellen + committen **vor** Container-Rebuild
- Pydantic Response-Schemas: `float` statt `Decimal`
- nginx SPA vs. Static-Dir: `location = /route` VOR `location /` einfügen
- Stunden-Anzeige: `formatHoursHM()` aus `utils/errorMessage.ts` (H:MM, Overflow-safe)
- Cross-Page Refresh nach Stempeln: `uiStore.notifyStampChange()` → `stampVersion` Effect
- Bulk-Deletes: `synchronize_session=False` + expliziter `tenant_id`-Filter
- **Überstundenausgleich:** Soll bleibt, Ist=0h (NICHT Soll reduzieren!)
- **Absence-Typ-Matrix:** Siehe `docs/BACKEND-ARCHITEKTUR.md` → Berechnungsmodell
- **CR-Approval:** Precondition-Checks VOR Status-Änderung (Race-Condition-Fix)
- **Absence-CRs:** MA können Abwesenheiten per Änderungsantrag beantragen (entry_kind="absence")
- **Absences Start/End:** Absences haben optionale `start_time`/`end_time` (NULL = ganzer Tag)
- **DSGVO Art.9:** Kalender-Endpoints maskieren `sick` → `absent` für nicht-Admins
- **§5 ArbZG:** Echtzeit-Ruhezeitwarnung beim Einstempeln (<11h seit letztem Arbeitsende)
- **net_hours Floor:** Kann nicht negativ werden (max(0, ...))
- **Export Multi-Entry:** Mehrere Einträge pro Tag werden korrekt exportiert

### Multi-Tenant
- **Jede neue Tabelle** braucht `tenant_id` FK + RLS-Policy + Eintrag in Migration
- **Neue Endpoints:** `set_tenant_context(db, tid)` oder `set_superadmin_context(db)` aufrufen
- **Neue Sessions** (`SessionLocal()` direkt): RLS-Kontext setzen, sonst 0 Rows!
- **DB-User:** App = `praxiszeit_app` (RLS enforced), Migrations = `praxiszeit` (Superuser)
- **JWT:** `tid` Claim enthält tenant_id, Middleware validiert gegen DB
- Default-Tenant UUID: `00000000-0000-0000-0000-000000000001`

### Standard-Benutzer (Dev)
- Admin: `admin` / `Admin2025!`
- Mitarbeiter: `manuel@klotz-roedig.de`

## Weiterführende Docs

| Thema | Datei |
|-------|-------|
| Deployment & Prod | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| Infrastruktur (Docker, nginx, Caddy, Mail, Monitoring) | [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) |
| Backend-Architektur (Router, Services, Patterns) | [docs/BACKEND-ARCHITEKTUR.md](docs/BACKEND-ARCHITEKTUR.md) |
| Architektur-Überblick (ARC42) | [docs/ARC42.md](docs/ARC42.md) |
| Installation | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| Security | [docs/SECURITY.md](docs/SECURITY.md) |
| Admin-Handbuch | [docs/handbuch/HANDBUCH-ADMIN.md](docs/handbuch/HANDBUCH-ADMIN.md) |
| Admin-Cheat-Sheet | [docs/handbuch/CHEATSHEET-ADMIN.md](docs/handbuch/CHEATSHEET-ADMIN.md) |
| Specs & Design-Docs | `docs/specs/` (arbzg, dsgvo, features, security) |

---
*Entwickelt mit Claude Sonnet 4.5, Sonnet 4.6 & Opus 4.6*
