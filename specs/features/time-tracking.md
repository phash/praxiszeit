# Spec: Zeiterfassung

**Status:** Done
**Erstellt:** 2026-02-01
**Zuletzt aktualisiert:** 2026-02-17

---

## Überblick

Mitarbeiter erfassen täglich ihre Arbeitszeiten (Start, Ende, Pause) mit optionalen Notizen. Die Wochenansicht zeigt Soll/Ist-Vergleich und Saldo. Admins können Zeiteinträge aller Mitarbeiter einsehen und bearbeiten.

---

## Requirements

### Funktionale Anforderungen

Als **Mitarbeiter** möchte ich meine tägliche Arbeitszeit erfassen, damit Über-/Unterstunden korrekt berechnet werden.

- [x] **REQ-1**: Zeiteintrag erstellen mit: Datum, Startzeit, Endzeit, Pausenminuten, Notiz
- [x] **REQ-2**: Wochenansicht mit Montag–Sonntag, navigierbar mit Prev/Next
- [x] **REQ-3**: Soll-Stunden basierend auf Arbeitstag (Wochenstunden / 5), ausgenommen Wochenenden und Feiertage
- [x] **REQ-4**: Ist-Stunden = (Endzeit – Startzeit) – Pause
- [x] **REQ-5**: Tages-Saldo = Ist – Soll
- [x] **REQ-6**: Wochen-Gesamtzeile mit Summen
- [x] **REQ-7**: Zeiteintrag bearbeiten und löschen
- [x] **REQ-8**: Admin kann Zeiteinträge aller Mitarbeiter sehen (`user_id` Query-Parameter)
- [x] **REQ-9**: Stempeluhr (Stamp Widget) auf Dashboard: Einloggen/Ausloggen per Knopfdruck
- [x] **REQ-10**: Historische Stundenänderungen korrekt berücksichtigen (Tag-für-Tag)

### Nicht-funktionale Anforderungen

- [x] Zeitberechnung auf Minutenbasis
- [x] Historische Wochenstunden via `working_hours_changes` (nicht `user.weekly_hours` direkt)
- [x] Feiertage von Datenbank geladen (nicht hardcodiert)

### Out of Scope

- Automatische Zeiterfassung (z.B. via Computer-Login)
- Projektbezogene Zeiterfassung

---

## Design

### Datenbank

```sql
CREATE TABLE time_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) NOT NULL,
    date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    break_minutes INTEGER NOT NULL DEFAULT 0,
    notes VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
-- Indexes: user_id, date, (user_id, date)
```

### Backend (FastAPI)

| Methode | Pfad | Auth | Beschreibung |
|---------|------|------|-------------|
| `GET` | `/api/time-entries` | Employee | Einträge (filter: user_id, start_date, end_date) |
| `POST` | `/api/time-entries` | Employee | Neuer Eintrag |
| `PUT` | `/api/time-entries/{id}` | Employee | Bearbeiten (eigene oder Admin) |
| `DELETE` | `/api/time-entries/{id}` | Employee | Löschen |

**Betroffene Dateien:**
- `backend/app/models/time_entry.py`
- `backend/app/schemas/time_entry.py`
- `backend/app/routers/time_entries.py`
- `backend/app/services/calculation_service.py`

### Kernlogik: `calculation_service.py`

```python
# RICHTIG: Tag-für-Tag, historisch korrekt
for day in date_range:
    weekly_hours = get_weekly_hours_for_date(db, user, day)
    daily_target = weekly_hours / 5  # wenn kein Feiertag/Wochenende

# FALSCH: Monatsmittelwert
avg = user.weekly_hours
```

---

## Tasks

- [x] **T-1**: Time Entry Model + Migration (001)
- [x] **T-2**: Calculation Service (get_weekly_hours_for_date, get_monthly_target/actual/balance)
- [x] **T-3**: Time Entries Router (CRUD)
- [x] **T-4**: Frontend Wochenansicht
- [x] **T-5**: Stempeluhr (StampWidget)
