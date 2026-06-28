# Spec: Feiertage & Betriebsferien

**Status:** Done
**Erstellt:** 2026-02-01
**Zuletzt aktualisiert:** 2026-06-28
**Zugehörige Issues:** #7, #143 (Custom-Feiertage), #175 (workalendar → python-holidays)

---

## Überblick

Gesetzliche Feiertage werden automatisch synchronisiert (konfigurierbar pro Bundesland) und in allen Berechnungen berücksichtigt. Betriebsferien werden als Abwesenheiten für alle Mitarbeiter angelegt (siehe `absences.md`).

---

## Requirements

- [x] **REQ-1**: Feiertage aus der `python-holidays`-Bibliothek (Paket `holidays`)
  automatisch synchronisiert. *(Migration von `workalendar` in #175 — workalendar
  ist seit 2023 unmaintained; python-holidays bildet die aktuellen
  Bundesland-Feiertage korrekt ab, z. B. MV-Frauentag ab 2023.)*
- [x] **REQ-2**: Bundesland ist ein **tenant-scoped Runtime-Setting**
  (`system_settings`-Key `holiday_state`), vom Admin im UI änderbar (`PUT
  /api/admin/settings/holiday_state`). Die `HOLIDAY_STATE`-Env-Variable (Standard:
  Bayern) ist nur der **Seed-Default**, der greift, solange/kein gültiger
  Tenant-Wert hinterlegt ist (`holiday_service.get_holiday_state`).
- [x] **REQ-3**: Alle 16 deutschen Bundesländer unterstützt
- [x] **REQ-4**: Feiertagsnamen auf Deutsch
- [x] **REQ-5**: Sync beim App-Start: aktuelles + nächstes Jahr
- [x] **REQ-6**: Endpunkt um verfügbare Bundesländer abzufragen
- [x] **REQ-7**: Feiertage werden bei Zeitraum-Abwesenheiten automatisch ausgeschlossen
- [x] **REQ-8**: In Soll-Stunden-Berechnung: Feiertage = 0 Soll

---

## Design

### Datenbank

```sql
CREATE TABLE public_holidays (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    name VARCHAR(200) NOT NULL,
    state VARCHAR(50) NOT NULL DEFAULT 'Bayern',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- Indexes: date, state
```

### Backend (FastAPI)

| Methode | Pfad | Auth | Beschreibung |
|---------|------|------|-------------|
| `GET` | `/api/holidays` | Employee | Feiertage für Jahr |
| `GET` | `/api/holidays/states` | Employee | Verfügbare Bundesländer |
| `POST` | `/api/holidays/sync` | Admin | Manuell synchronisieren |

**Betroffene Dateien:**
- `backend/app/models/public_holiday.py`
- `backend/app/routers/holidays.py`
- `backend/app/services/holiday_service.py`
- `backend/app/routers/admin_settings.py` (`holiday_state` in `_ALLOWED_SETTINGS`;
  `PUT` validiert gegen `SUPPORTED_STATES` + löst atomaren Resync aus)
- `backend/app/config.py` (`HOLIDAY_STATE` = Seed-Default; aus TOML `[practice].holiday_state` befüllbar)

> **Bundesland ändern (`PUT /api/admin/settings/holiday_state`):** validiert gegen
> `SUPPORTED_STATES`, dann atomar in **einer** Transaktion `delete_all_holidays(
> source="workalendar")` + `sync_current_and_next_year(state=…, tenant_id=…)`.

**Holiday Service (`holiday_service.py`, ab #175 python-holidays):**
```python
import holidays

# Bundesland-Name (UI/Setting) -> ISO-3166-2-Subdivision-Code
SUPPORTED_STATES = {
    "Bayern": "BY", "Berlin": "BE", "Baden-Württemberg": "BW",
    # ... alle 16 Bundesländer
}

# python-holidays liefert mit language="de" deutsche Namen; nur wenige
# werden auf die Projekt-Schreibweise normalisiert (kein Re-Naming bei Resync):
_NAME_NORMALIZE = {
    "Erster Mai": "Tag der Arbeit",
    "Erster Weihnachtstag": "1. Weihnachtstag",
    "Zweiter Weihnachtstag": "2. Weihnachtstag",
    "Frauentag": "Internationaler Frauentag",
}

def _holidays_for(year: int, code: str):
    kwargs = {"years": year, "subdiv": code, "language": "de"}
    if code == "BY":
        # Bayern: katholische Feiertage (z. B. Mariä Himmelfahrt) mitnehmen
        kwargs["categories"] = ("public", "catholic")
    return holidays.Germany(**kwargs)

def get_holiday_state(db: Session, tenant_id=None) -> str:
    # liest holiday_state aus system_settings (tenant-scoped),
    # Fallback auf settings.HOLIDAY_STATE (Env/TOML)

def sync_holidays(db: Session, year: int, state, tenant_id=None) -> int:
    # Lädt Feiertage via python-holidays, normalisiert Namen, speichert tenant-scoped
```

> **Custom-Feiertage (#143):** Ein Bundesland-Resync (`delete_all_holidays(...,
> source="workalendar")` + Re-Sync) entfernt **nur** auto-generierte Zeilen;
> admin-gepflegte Feiertage (`source="admin"`) überleben den Wechsel.

---

## Tasks

- [x] **T-1**: public_holidays Tabelle + Migration
- [x] **T-2**: Holiday Service mit python-holidays (vormals workalendar, #175)
- [x] **T-3**: Deutsche Namen via `language="de"` + `_NAME_NORMALIZE`-Overrides
- [x] **T-4**: Alle 16 Bundesländer (SUPPORTED_STATES, Name → ISO-Code)
- [x] **T-5**: `holiday_state` als tenant-scoped Runtime-Setting (Admin-UI); `HOLIDAY_STATE` nur Seed-Default in config.py
- [x] **T-6**: Holidays Router (list, states, sync)
- [x] **T-7**: App-Start: automatischer Sync
