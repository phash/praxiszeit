# Spec: Feiertage & Betriebsferien

**Status:** Done
**Erstellt:** 2026-02-01
**Zuletzt aktualisiert:** 2026-02-17
**Zugehörige Issues:** #7

---

## Überblick

Gesetzliche Feiertage werden automatisch synchronisiert (konfigurierbar pro Bundesland) und in allen Berechnungen berücksichtigt. Betriebsferien werden als Abwesenheiten für alle Mitarbeiter angelegt (siehe `absences.md`).

---

## Requirements

- [x] **REQ-1**: Feiertage aus `workalendar` Bibliothek automatisch synchronisiert
- [x] **REQ-2**: Bundesland konfigurierbar via `HOLIDAY_STATE` Env-Variable (Standard: Bayern)
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
- `backend/app/config.py` (HOLIDAY_STATE)

**Holiday Service:**
```python
HOLIDAY_NAME_DE = {
    "New year": "Neujahr",
    "Good Friday": "Karfreitag",
    "Easter Monday": "Ostermontag",
    # ... alle Feiertage
}

SUPPORTED_STATES = {
    "Bayern": GermanBavaria,
    "Berlin": GermanBerlin,
    # ... alle 16 Bundesländer
}

def sync_holidays(db: Session, year: int) -> None:
    # Lädt Feiertage via workalendar, übersetzt Namen, speichert in DB
```

---

## Tasks

- [x] **T-1**: public_holidays Tabelle + Migration
- [x] **T-2**: Holiday Service mit workalendar
- [x] **T-3**: Deutsche Übersetzungen (HOLIDAY_NAME_DE)
- [x] **T-4**: Alle 16 Bundesländer (SUPPORTED_STATES)
- [x] **T-5**: HOLIDAY_STATE in config.py
- [x] **T-6**: Holidays Router (list, states, sync)
- [x] **T-7**: App-Start: automatischer Sync
