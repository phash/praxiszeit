# Backend Test Coverage – Full Sweep Design

**Goal:** Vollständige Unit-Test-Abdeckung aller unbetesteten Backend-Services.

**Ansatz:** 4 neue Testdateien + Erweiterungen bestehender Tests. Reine Service-Unit-Tests mit SQLite In-Memory (kein HTTP-Layer, kein Docker).

**Tech Stack:** pytest, SQLAlchemy, SQLite In-Memory (bereits in conftest.py etabliert)

---

## Neue Testdateien

### 1. `tests/test_break_validation.py` (~15 Tests)

ArbZG §4 – Pausenvalidierung:
- ≤6h Arbeit → keine Pause erforderlich (kein Fehler)
- >6h ohne Pause → Fehler (30min)
- >6h mit ≥30min → kein Fehler
- >9h mit <45min → Fehler (45min)
- >9h mit ≥45min → kein Fehler
- Gaps zwischen Einträgen zählen als Pausen
- Mehrere Einträge kumuliert (gleicher Tag)
- `exclude_entry_id` überspringt bestehenden Eintrag beim Update
- Exakte Grenzen: genau 6h = kein Fehler, genau 9h = 30min reicht

### 2. `tests/test_rest_time.py` (~10 Tests)

ArbZG §5 – Ruhezeit:
- Keine Einträge → keine Verstöße
- >11h Ruhezeit → kein Verstoß
- <11h Ruhezeit → Verstoß mit korrekten Feldern (day1_date, day2_date, actual_rest_hours, deficit_hours)
- Split Shifts (mehrere Einträge selber Tag) → kein False Positive
- Mehrere Verstöße im Monat
- Monatsfilter (nur gefilterte Monate prüfen)
- Custom `min_rest_hours` Parameter

### 3. `tests/test_holiday_service.py` (~10 Tests)

- `is_holiday` → True für eingetragenen Feiertag
- `is_holiday` → False für Nicht-Feiertag
- `get_holiday_state` → liest aus DB-SystemSetting
- `get_holiday_state` → Fallback auf settings.HOLIDAY_STATE wenn kein DB-Eintrag
- `delete_all_holidays` → löscht alle Einträge, kein db.commit() (Transaktion bleibt offen)
- `sync_holidays` → fügt Feiertage ein, kein db.commit()
- `sync_holidays` → updated Namen existierender Einträge
- `sync_current_and_next_year` → committet genau einmal, gibt dict mit counts zurück

### 4. `tests/test_calculations_extended.py` (~25 Tests)

Lücken in `calculation_service.py`:

**`get_weekly_hours_for_date`:**
- Kein historischer Eintrag → `user.weekly_hours`
- Historischer Eintrag vor Datum → historische Stunden
- Historischer Eintrag nach Datum → ignoriert, `user.weekly_hours`

**`get_daily_target_for_date`:**
- Wochentag (Mo–Fr) → korrekte Stunden
- Wochenende (Sa, So) → 0
- `use_daily_schedule=True` → tagespezifische Stunden

**`get_working_days_in_month`:**
- Januar 2026 → 22 Werktage (korrekte Anzahl)

**`get_monthly_target` Erweiterungen:**
- Mit Feiertag → Feiertag reduziert Soll
- Mit VACATION Abwesenheit → reduziert Soll
- Mit TRAINING Abwesenheit → reduziert Soll NICHT (außer Haus)
- Mit OVERTIME Abwesenheit → reduziert Soll

**`get_vacation_account` pro-rata (Audit-Fix!):**
- `first_work_day` im laufenden Jahr → reduziertes Budget
- `last_work_day` im laufenden Jahr → reduziertes Budget
- Beide gesetzt im gleichen Jahr → minimum der beiden
- Tagesgenaue Berechnung (15. März ≠ ganzer März)

**`count_workdays` (neu, Audit-Fix!):**
- Einfacher Bereich ohne Feiertage
- Mit Feiertag → Feiertag ausgeschlossen
- Wochenenden ausgeschlossen
- Monatsübergreifender Bereich

**`get_overtime_account`:**
- Mit mehreren Monaten und tatsächlichen Einträgen → kumulierter Saldo

---

## Fixtures (Erweiterungen für conftest.py)

```python
@pytest.fixture
def public_holiday(db):
    """Ein Feiertag für Tests."""
    ...

@pytest.fixture
def working_hours_change(db, test_user):
    """Historische Arbeitsstunden-Änderung."""
    ...
```

---

## Erfolgskriterien

- Alle ~60 neuen Tests grün
- `pytest tests/ -v` läuft durch ohne Fehler
- Keine Änderungen an Produktionscode
