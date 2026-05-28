# Spec: Lokale/regionale Feiertage anlegen (Custom Holidays)

**Status:** Ready
**Erstellt:** 2026-05-28
**Zuletzt aktualisiert:** 2026-05-28
**Zugehörige Issues:** #143

---

## Überblick

Admins sollen zusätzliche, lokal-regionale Feiertage (z.B. Schützenfest, Karneval) erfassen können, die nicht von der `workalendar`-Bundesland-Logik abgedeckt sind. Custom-Feiertage reduzieren die Soll-Zeit wie reguläre Feiertage und überstehen einen Bundesland-Resync. Grundlage: `feedback/feedback_01.txt`, Punkt 5.

---

## Requirements

### Funktionale Anforderungen

Als **Admin** möchte ich **eigene Feiertage pro Datum anlegen, bearbeiten und löschen**, damit **regionale Besonderheiten korrekt in der Sollzeit berücksichtigt werden**.

- [ ] **REQ-1**: Admin kann einen Custom-Feiertag mit Name + konkretem Datum anlegen.
- [ ] **REQ-2**: Admin kann eigene Feiertage bearbeiten und löschen. Standard-(`workalendar`-)Feiertage sind **nicht** editier-/löschbar.
- [ ] **REQ-3**: Ein Bundesland-Wechsel-Resync löscht Custom-Feiertage **nicht**.
- [ ] **REQ-4**: Custom-Feiertage reduzieren die Soll-Zeit identisch zu Standard-Feiertagen.

### Nicht-funktionale Anforderungen

- [ ] Sicherheit: Schreib-Endpunkte nur Admin; tenant-scoped (F-026, PublicHoliday immer mit `tenant_id`).
- [ ] Validierung: kein Duplikat (gleiches Datum + `tenant_id`); Name nicht leer.

### Out of Scope

- Jährlich automatisch wiederkehrende Feiertage / Berechnung beweglicher Feste (Entscheidung: pro Datum/Jahr einzeln).
- Halbe Feiertage (24./31.12. → #146).

---

## Design

### Datenbank

```sql
ALTER TABLE public_holidays ADD COLUMN is_custom BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public_holidays ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'workalendar';
-- source ∈ {'workalendar','admin'}
```

`PublicHoliday`-Model (`models/public_holiday.py`) heute: `id, tenant_id, date, name, year`. → Felder `is_custom`, `source` ergänzen.

**Migration:** `backend/alembic/versions/YYYY_MM_DD_HHMM-NNN_add_custom_holiday_fields.py` (Revision-ID ≤ 32 Zeichen).

### Backend (FastAPI)

**Betroffene Dateien:** `backend/app/routers/holidays.py`, `holiday_service.py`, `admin_settings.py`

| Methode | Pfad | Auth | Beschreibung |
|---------|------|------|-------------|
| `POST` | `/api/holidays` | Admin | Custom-Feiertag anlegen (`is_custom=true, source='admin'`) |
| `PUT` | `/api/holidays/{id}` | Admin | Nur wenn `is_custom=true` |
| `DELETE` | `/api/holidays/{id}` | Admin | Nur wenn `is_custom=true`, sonst 403 |

- `GET /api/holidays` bleibt; liefert Custom + Standard gemeinsam (Custom z.B. mit Flag markiert).
- **Resync-Schutz** (`holiday_service.py` / `admin_settings.py`): der Resync bei Bundesland-Wechsel löscht/ersetzt nur Einträge mit `source='workalendar'`; `source='admin'` bleibt erhalten.
- **Sollzeit:** `calculation_service` zählt Feiertage bereits über `PublicHoliday` — Custom-Feiertage wirken automatisch, sofern sie in derselben Tabelle liegen (verifizieren, dass kein `source`-Filter die Custom-Einträge ausschließt).

**Schemas:** `HolidayCreate` (name, date), `HolidayUpdate`, `HolidayResponse` (+ `is_custom`).

### Frontend (React/TypeScript)

- Admin-UI zum Verwalten eigener Feiertage — Verortung: bei den Feiertags-/Bundesland-Einstellungen (`Settings.tsx`) oder im Abwesenheits-/Kalenderbereich.
- Liste aller Feiertage des Jahres; Standard-Feiertage read-only (kein Edit/Delete), Custom mit Bearbeiten/Löschen.
- Formular: Name + Datum (Datepicker).

---

## Tasks

### Backend
- [ ] **T-1**: Migration `add_custom_holiday_fields` (`is_custom`, `source`).
- [ ] **T-2**: `PublicHoliday`-Model + Schemas erweitern.
- [ ] **T-3**: `POST`/`PUT`/`DELETE`-Endpunkte (Admin, tenant-scoped, nur `is_custom`).
- [ ] **T-4**: Resync-Logik so anpassen, dass nur `source='workalendar'` betroffen ist.
- [ ] **T-5**: Verifizieren, dass `calculation_service` Custom-Feiertage in der Sollzeit berücksichtigt.

### Frontend
- [ ] **T-6**: Feiertags-Verwaltungs-UI (Liste + CRUD für Custom).
- [ ] **T-7**: Route/Nav falls eigene Seite nötig.

### Tests & Qualität
- [ ] **T-8**: Backend-Test: Custom anlegen → reduziert Sollzeit; Standard nicht löschbar (403); Resync behält Custom.
- [ ] **T-9**: E2E: Custom-Feiertag anlegen → erscheint im Kalender, Sollzeit korrekt.
- [ ] **T-10**: Builds/Tests grün.

### Abschluss
- [ ] **T-11**: Spec aktualisieren, Commit & Push.

---

## Offene Fragen

1. Anzeige im Mitarbeiter-Kalender: Custom-Feiertage visuell von Standard unterscheiden (eigene Farbe/Label)? → Vorschlag: gleiche Darstellung wie Standard-Feiertag, Name genügt.

---

## Notizen

- Standard-Seeding via `workalendar` pro Bundesland (`holiday_service.py`); regionale Standard-Feiertage (Fronleichnam etc.) sind dadurch bereits abgedeckt.
- CLAUDE.md-Regel beachten: `is_holiday()` / alle PublicHoliday-Queries mit `tenant_id`.
