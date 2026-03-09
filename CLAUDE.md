# CLAUDE.md – PraxisZeit

**Vor dem Arbeiten:** Lese die Memory-Dateien unter `C:\Users\manue\.claude\projects\E--claude-zeiterfassung-praxiszeit\memory\`:

| Datei | Inhalt |
|-------|--------|
| `MEMORY.md` | Kritische Regeln, Test-User, Topic-Index |
| `architecture.md` | Stack, Ordnerstruktur, API-Übersicht, Patterns |
| `database.md` | Schema (alle Tabellen), Migrationen, Gotchas |
| `business-logic.md` | calculation_service, ArbZG-Compliance, Security/JWT |
| `dev-workflow.md` | Docker-Befehle, Testing, Deployment, Troubleshooting |

---

## Schnellreferenz

**Repo:** https://github.com/phash/praxiszeit
**Stack:** React 18 + TypeScript + Tailwind / FastAPI (Python 3.12) + PostgreSQL 16 / Docker Compose

### Start
```bash
docker-compose up -d    # Frontend :80, API-Docs :8000/docs
docker-compose down
```

### Kritische Regeln
- `get_weekly_hours_for_date()` **immer** pro Tag – nie `user.weekly_hours` direkt
- Migrationen auf Host erstellen + committen **vor** Container-Rebuild
- Pydantic Response-Schemas: `float` statt `Decimal`
- `docs/generated/` ist gitignored

### Standard-Benutzer
- Admin: `admin@praxis.de`
- Test-Admin: `admin@example.com` / `admin123`
- Mitarbeiter: `manuel@klotz-roedig.de`

---
*Entwickelt mit Claude Sonnet 4.5, Sonnet 4.6 & Opus 4.6*
