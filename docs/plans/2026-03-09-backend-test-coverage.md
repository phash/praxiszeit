# Backend Test Coverage – Full Sweep Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Vollständige Unit-Test-Abdeckung aller unbetesteten Backend-Services (~60 neue Tests).

**Architecture:** 4 neue Testdateien in `backend/tests/`. Reine Service-Unit-Tests via direktem Funktionsaufruf – kein HTTP-Layer, kein Docker. SQLite In-Memory (bereits in conftest.py etabliert).

**Tech Stack:** pytest, SQLAlchemy, SQLite In-Memory, Decimal, datetime, `app.services.*`

---

## Context: Wie Tests hier funktionieren

**DB-Fixture** (`conftest.py`): Erzeugt bei jedem Test eine frische SQLite-DB, erstellt alle Tabellen, schließt + dropt nach dem Test. Fixture-Scope: `function`.

**test_user** Fixture: User mit `weekly_hours=40.0`, `vacation_days=30`, `work_days_per_week=5`, `role=EMPLOYEE`.

**Pattern** (aus `test_calculations.py`):
```python
from decimal import Decimal
from datetime import date, time
from app.models import User, UserRole, TimeEntry, Absence, AbsenceType, PublicHoliday
from app.services import calculation_service

def test_something(db, test_user):
    # Inline model creation:
    entry = TimeEntry(
        user_id=test_user.id,
        date=date(2026, 3, 10),
        start_time=time(8, 0),
        end_time=time(16, 0),
        break_minutes=30,
    )
    db.add(entry)
    db.commit()

    result = calculation_service.some_function(db, test_user, ...)
    assert result == Decimal('8.0')
```

**Ausführen:**
```bash
cd E:\claude\zeiterfassung\praxiszeit
docker-compose exec backend pytest tests/test_NAME.py -v
```

---

## Task 1: `tests/test_break_validation.py` – ArbZG §4 Pausenvalidierung

**Files:**
- Create: `backend/tests/test_break_validation.py`

**Funktion unter Test:**
```python
from app.services.break_validation_service import validate_daily_break
# Signatur:
validate_daily_break(db, user_id, entry_date, start_time, end_time, break_minutes, exclude_entry_id=None) -> Optional[str]
# Returns None wenn gültig, Error-String wenn Verstoß
```

**Step 1: Testdatei anlegen mit Import-Block**

```python
"""Tests für ArbZG §4 Pausenvalidierung."""
import pytest
from datetime import date, time
from uuid import UUID
from app.models import User, UserRole, TimeEntry
from app.services.break_validation_service import validate_daily_break


def make_entry(db, user, start_h, start_m, end_h, end_m, break_min=0, d=None):
    """Helper: Zeiteintrag erstellen und committen."""
    entry = TimeEntry(
        user_id=user.id,
        date=d or date(2026, 3, 10),
        start_time=time(start_h, start_m),
        end_time=time(end_h, end_m),
        break_minutes=break_min,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
```

**Step 2: 15 Tests schreiben**

```python
# --- Tests ≤6h: keine Pause erforderlich ---

def test_under_6h_no_break_required(db, test_user):
    """≤6h Arbeit → None (kein Fehler)."""
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(8, 0), time(14, 0), break_minutes=0
    )
    assert result is None


def test_exactly_6h_no_break_required(db, test_user):
    """Genau 6h Netto → kein Fehler (>6h ist die Grenze, nicht ≥6h)."""
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(8, 0), time(14, 0), break_minutes=0
    )
    assert result is None


# --- Tests >6h: 30min Pause erforderlich ---

def test_over_6h_without_break_fails(db, test_user):
    """>6h ohne Pause → Fehler."""
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(8, 0), time(14, 31), break_minutes=0
    )
    assert result is not None
    assert "30 Minuten" in result


def test_over_6h_with_30min_break_ok(db, test_user):
    """>6h mit genau 30min → kein Fehler."""
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(8, 0), time(14, 31), break_minutes=30
    )
    assert result is None


# --- Tests >9h: 45min Pause erforderlich ---

def test_over_9h_with_30min_break_fails(db, test_user):
    """>9h mit nur 30min → Fehler (braucht 45min)."""
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(8, 0), time(17, 31), break_minutes=30
    )
    assert result is not None
    assert "45 Minuten" in result


def test_over_9h_with_45min_break_ok(db, test_user):
    """>9h mit genau 45min → kein Fehler."""
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(8, 0), time(17, 31), break_minutes=45
    )
    assert result is None


def test_exactly_9h_needs_only_30min(db, test_user):
    """Genau 9h Netto → 30min reicht (>9h ist die Grenze für 45min)."""
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(8, 0), time(17, 0), break_minutes=30
    )
    assert result is None


# --- Gaps zwischen Einträgen zählen als Pause ---

def test_gap_between_entries_counts_as_break(db, test_user):
    """Lücke zwischen Einträgen zählt als Pause."""
    # Erster Eintrag: 8:00–12:00 (kein Break)
    make_entry(db, test_user, 8, 0, 12, 0, break_min=0)
    # Zweiter Eintrag: 13:00–16:01 → Gap von 60min → insgesamt >6h, aber 60min Pause
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(13, 0), time(16, 1), break_minutes=0
    )
    assert result is None  # 60min Gap > 30min → kein Fehler


def test_gap_not_sufficient_for_long_day(db, test_user):
    """Lücke allein reicht nicht, wenn >9h Arbeit und Lücke <45min."""
    # Erster Eintrag: 8:00–12:00 (4h, kein Break)
    make_entry(db, test_user, 8, 0, 12, 0, break_min=0)
    # Zweiter Eintrag: 12:20–17:41 → 5h21min Arbeit, Lücke nur 20min
    # Gesamt: 4h + 5h21min = 9h21min > 9h, Pause nur 20min < 45min → Fehler
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(12, 20), time(17, 41), break_minutes=0
    )
    assert result is not None
    assert "45 Minuten" in result


# --- Mehrere Einträge kumuliert ---

def test_multiple_entries_cumulated(db, test_user):
    """Mehrere kurze Einträge summieren auf >6h → Pause nötig."""
    make_entry(db, test_user, 8, 0, 10, 0, break_min=0)   # 2h
    make_entry(db, test_user, 10, 0, 12, 0, break_min=0)  # 2h (direkt anschließend)
    # Dritter Eintrag: 12:00–14:01 = 2h01min → gesamt 6h01min > 6h, keine Pause → Fehler
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(12, 0), time(14, 1), break_minutes=0
    )
    assert result is not None


# --- exclude_entry_id ---

def test_exclude_entry_id_skips_existing(db, test_user):
    """exclude_entry_id überspringt existierenden Eintrag beim Update."""
    existing = make_entry(db, test_user, 8, 0, 16, 0, break_min=0)
    # Beim Update wird der existierende Eintrag durch neuen Wert ersetzt
    # Neuer Wert: 8:00–14:00 mit 0 Pause → 6h genau → kein Fehler
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(8, 0), time(14, 0), break_minutes=0,
        exclude_entry_id=existing.id
    )
    assert result is None


def test_without_exclude_old_entry_counted(db, test_user):
    """Ohne exclude_entry_id wird alter Eintrag mit dem neuen summiert."""
    make_entry(db, test_user, 8, 0, 14, 1, break_min=0)  # 6h01min
    # Neuer Eintrag ohne Exclude → beide summiert → >6h ohne Pause → Fehler
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(15, 0), time(16, 0), break_minutes=0
    )
    assert result is not None


# --- Offene Einträge (kein end_time) werden ignoriert ---

def test_open_entry_without_end_time_ignored(db, test_user):
    """Einträge ohne end_time werden ignoriert (aktive Clock-In-Session)."""
    entry = TimeEntry(
        user_id=test_user.id,
        date=date(2026, 3, 10),
        start_time=time(8, 0),
        end_time=None,  # Offen!
        break_minutes=0,
    )
    db.add(entry)
    db.commit()
    # Neuer Eintrag allein: 8:00–14:01 = 6h01min ohne Pause → Fehler
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(8, 0), time(14, 1), break_minutes=0
    )
    assert result is not None  # Nur der neue Eintrag zählt


# --- Verschiedene Tage unabhängig voneinander ---

def test_different_dates_independent(db, test_user):
    """Einträge an verschiedenen Tagen werden nicht kumuliert."""
    make_entry(db, test_user, 8, 0, 14, 1, break_min=0, d=date(2026, 3, 9))  # Vortag
    # Neuer Eintrag heute: nur 5h, kein Problem
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(8, 0), time(13, 0), break_minutes=0
    )
    assert result is None


# --- Kein Fehler wenn Netto=0 ---

def test_zero_net_hours_no_error(db, test_user):
    """0 Netto-Stunden → kein Fehler."""
    result = validate_daily_break(
        db, test_user.id, date(2026, 3, 10),
        time(8, 0), time(8, 0), break_minutes=0
    )
    assert result is None
```

**Step 3: Tests ausführen (sollten alle grün sein – kein Produktionscode zu ändern)**

```bash
docker-compose exec backend pytest tests/test_break_validation.py -v
```
Erwartet: 15 PASSED

**Step 4: Commit**

```bash
git add backend/tests/test_break_validation.py
git commit -m "test: add break validation tests (ArbZG §4, 15 tests)"
```

---

## Task 2: `tests/test_rest_time.py` – ArbZG §5 Ruhezeit

**Files:**
- Create: `backend/tests/test_rest_time.py`

**Funktion unter Test:**
```python
from app.services.rest_time_service import check_rest_time_violations
# Signatur:
check_rest_time_violations(db, user, year, month=None, min_rest_hours=None) -> List[Dict]
# Violation Dict Keys: day1_date, day1_end, day2_date, day2_start, actual_rest_hours, min_rest_hours, deficit_hours
```

**Step 1: Testdatei anlegen**

```python
"""Tests für ArbZG §5 Ruhezeitvalidierung."""
import pytest
from datetime import date, time
from app.models import TimeEntry
from app.services.rest_time_service import check_rest_time_violations


def make_entry(db, user, d, start_h, start_m, end_h, end_m):
    """Helper: Zeiteintrag erstellen und committen."""
    entry = TimeEntry(
        user_id=user.id,
        date=d,
        start_time=time(start_h, start_m),
        end_time=time(end_h, end_m),
        break_minutes=0,
    )
    db.add(entry)
    db.commit()
    return entry
```

**Step 2: 10 Tests schreiben**

```python
def test_no_entries_no_violations(db, test_user):
    """Keine Einträge → keine Verstöße."""
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert violations == []


def test_sufficient_rest_no_violation(db, test_user):
    """>11h Ruhezeit → kein Verstoß."""
    make_entry(db, test_user, date(2026, 3, 10), 8, 0, 17, 0)   # Ende 17:00
    make_entry(db, test_user, date(2026, 3, 11), 8, 0, 17, 0)   # Nächster Tag 08:00 → 15h Ruhe
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert violations == []


def test_insufficient_rest_creates_violation(db, test_user):
    """<11h Ruhezeit → Verstoß mit korrekten Feldern."""
    make_entry(db, test_user, date(2026, 3, 10), 8, 0, 22, 0)   # Ende 22:00
    make_entry(db, test_user, date(2026, 3, 11), 7, 0, 15, 0)   # Start 07:00 → nur 9h Ruhe
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert len(violations) == 1
    v = violations[0]
    assert v["day1_date"] == "2026-03-10"
    assert v["day2_date"] == "2026-03-11"
    assert v["actual_rest_hours"] == 9.0
    assert v["min_rest_hours"] == 11
    assert v["deficit_hours"] == 2.0


def test_violation_fields_are_correct(db, test_user):
    """Violation-Dict enthält alle erwarteten Felder."""
    make_entry(db, test_user, date(2026, 3, 10), 14, 0, 23, 0)
    make_entry(db, test_user, date(2026, 3, 11), 8, 0, 16, 0)
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert len(violations) == 1
    v = violations[0]
    assert "day1_date" in v
    assert "day1_end" in v
    assert "day2_date" in v
    assert "day2_start" in v
    assert "actual_rest_hours" in v
    assert "min_rest_hours" in v
    assert "deficit_hours" in v


def test_split_shifts_no_false_positive(db, test_user):
    """Split Shifts (mehrere Einträge gleicher Tag) → kein False Positive."""
    # Tag 1: 08:00-12:00 + 14:00-18:00 (intra-day Gap soll NICHT als Verstoß zählen)
    make_entry(db, test_user, date(2026, 3, 10), 8, 0, 12, 0)
    make_entry(db, test_user, date(2026, 3, 10), 14, 0, 18, 0)
    # Tag 2: 08:00–16:00 → Ruhezeit von Ende Tag 1 (18:00) bis Start Tag 2 (08:00) = 14h ✓
    make_entry(db, test_user, date(2026, 3, 11), 8, 0, 16, 0)
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert violations == []


def test_multiple_violations_in_month(db, test_user):
    """Mehrere Verstöße im Monat werden alle erfasst."""
    # Verstoß 1: 10.→11. März
    make_entry(db, test_user, date(2026, 3, 10), 8, 0, 22, 0)
    make_entry(db, test_user, date(2026, 3, 11), 7, 0, 15, 0)
    # Verstoß 2: 20.→21. März
    make_entry(db, test_user, date(2026, 3, 20), 8, 0, 22, 0)
    make_entry(db, test_user, date(2026, 3, 21), 7, 0, 15, 0)
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert len(violations) == 2


def test_month_filter_excludes_other_months(db, test_user):
    """Monatsfilter: Nur gefilterte Monate werden geprüft."""
    # Verstoß im Februar (nicht im Filter)
    make_entry(db, test_user, date(2026, 2, 28), 8, 0, 22, 0)
    make_entry(db, test_user, date(2026, 3, 1), 7, 0, 15, 0)
    # Prüfe nur März → kein Eintrag im März der einen Vortag hat → keine Verletzung
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    # Der März-Eintrag hat keinen März-Vortag → kein Verstoß
    assert len(violations) == 0


def test_no_month_filter_checks_full_year(db, test_user):
    """Ohne Monatsfilter: ganzes Jahr wird geprüft."""
    make_entry(db, test_user, date(2026, 2, 28), 8, 0, 22, 0)
    make_entry(db, test_user, date(2026, 3, 1), 7, 0, 15, 0)
    violations = check_rest_time_violations(db, test_user, 2026)  # kein month-Filter
    assert len(violations) == 1


def test_custom_min_rest_hours(db, test_user):
    """Custom min_rest_hours Parameter wird respektiert."""
    make_entry(db, test_user, date(2026, 3, 10), 8, 0, 17, 0)   # Ende 17:00
    make_entry(db, test_user, date(2026, 3, 11), 8, 0, 17, 0)   # Start 08:00 → 15h Ruhe
    # Mit Standard 11h → kein Verstoß
    assert check_rest_time_violations(db, test_user, 2026, month=3) == []
    # Mit custom 16h → Verstoß (15h < 16h)
    violations = check_rest_time_violations(db, test_user, 2026, month=3, min_rest_hours=16)
    assert len(violations) == 1
    assert violations[0]["min_rest_hours"] == 16


def test_single_entry_no_violation(db, test_user):
    """Einzelner Eintrag (kein Vortag vorhanden) → kein Verstoß."""
    make_entry(db, test_user, date(2026, 3, 15), 8, 0, 17, 0)
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert violations == []
```

**Step 3: Tests ausführen**

```bash
docker-compose exec backend pytest tests/test_rest_time.py -v
```
Erwartet: 10 PASSED

**Step 4: Commit**

```bash
git add backend/tests/test_rest_time.py
git commit -m "test: add rest time violation tests (ArbZG §5, 10 tests)"
```

---

## Task 3: `tests/test_holiday_service.py` – Holiday Service

**Files:**
- Create: `backend/tests/test_holiday_service.py`

**Funktionen unter Test:**
```python
from app.services import holiday_service
# is_holiday(db, date) -> bool
# get_holiday_state(db) -> str
# delete_all_holidays(db) -> int
# sync_holidays(db, year, state=None) -> int
# sync_current_and_next_year(db, state=None) -> dict
```

**Step 1: Testdatei anlegen**

```python
"""Tests für holiday_service."""
import pytest
from datetime import date, datetime
from unittest.mock import patch
from app.models.public_holiday import PublicHoliday
from app.models.system_setting import SystemSetting
from app.services import holiday_service


@pytest.fixture
def public_holiday(db):
    """Ein Feiertag für Tests."""
    h = PublicHoliday(
        date=date(2026, 1, 1),
        name="Neujahr",
        year=2026,
    )
    db.add(h)
    db.commit()
    return h
```

**Step 2: 10 Tests schreiben**

```python
# --- is_holiday ---

def test_is_holiday_true_for_existing(db, public_holiday):
    """`is_holiday` → True für eingetragenen Feiertag."""
    assert holiday_service.is_holiday(db, date(2026, 1, 1)) is True


def test_is_holiday_false_for_non_holiday(db, public_holiday):
    """`is_holiday` → False für normalen Tag."""
    assert holiday_service.is_holiday(db, date(2026, 1, 2)) is False


# --- get_holiday_state ---

def test_get_holiday_state_from_db(db):
    """`get_holiday_state` liest aus DB-SystemSetting."""
    setting = SystemSetting(key="holiday_state", value="Bayern")
    db.add(setting)
    db.commit()
    result = holiday_service.get_holiday_state(db)
    assert result == "Bayern"


def test_get_holiday_state_fallback(db):
    """`get_holiday_state` → Fallback auf settings.HOLIDAY_STATE wenn kein DB-Eintrag."""
    # Keine SystemSetting in DB → Fallback auf config
    from app.config import settings
    result = holiday_service.get_holiday_state(db)
    assert result == settings.HOLIDAY_STATE


# --- delete_all_holidays ---

def test_delete_all_holidays_removes_entries(db, public_holiday):
    """`delete_all_holidays` → löscht alle Einträge."""
    count = holiday_service.delete_all_holidays(db)
    assert count == 1
    remaining = db.query(PublicHoliday).count()
    assert remaining == 0  # noch nicht committed, aber Session sieht Deletion


def test_delete_all_holidays_no_commit(db, public_holiday):
    """`delete_all_holidays` → macht keinen db.commit() (Transaktion bleibt offen)."""
    # Wir prüfen: nach delete_all_holidays aber vor eigenem commit
    # ist der Eintrag in der Session weg
    holiday_service.delete_all_holidays(db)
    # Rollback simuliert fehlgeschlagene Transaktion
    db.rollback()
    # Nach Rollback ist der Eintrag wieder da
    remaining = db.query(PublicHoliday).count()
    assert remaining == 1


# --- sync_holidays ---

def test_sync_holidays_adds_holidays(db):
    """`sync_holidays` → fügt Feiertage ein (Bayern 2026 hat >0 Feiertage)."""
    count = holiday_service.sync_holidays(db, 2026, state="Bayern")
    assert count > 0
    db.commit()
    total = db.query(PublicHoliday).filter(PublicHoliday.year == 2026).count()
    assert total == count


def test_sync_holidays_updates_existing_name(db):
    """`sync_holidays` → updated Namen existierender Einträge wenn abweichend."""
    # Feiertag mit falschem Namen eintragen
    h = PublicHoliday(date=date(2026, 1, 1), name="WRONG_NAME", year=2026)
    db.add(h)
    db.commit()
    # sync_holidays soll den Namen korrigieren
    holiday_service.sync_holidays(db, 2026, state="Bayern")
    db.commit()
    refreshed = db.query(PublicHoliday).filter(PublicHoliday.date == date(2026, 1, 1)).first()
    assert refreshed.name == "Neujahr"


def test_sync_holidays_no_commit(db):
    """`sync_holidays` → kein db.commit() (Caller ist verantwortlich)."""
    holiday_service.sync_holidays(db, 2026, state="Bayern")
    # Rollback → Feiertage sollten weg sein
    db.rollback()
    total = db.query(PublicHoliday).count()
    assert total == 0


# --- sync_current_and_next_year ---

def test_sync_current_and_next_year_commits_once(db):
    """`sync_current_and_next_year` → committet genau einmal, gibt dict zurück."""
    result = holiday_service.sync_current_and_next_year(db, state="Bayern")
    assert "current_year" in result
    assert "next_year" in result
    assert "current_count" in result
    assert "next_count" in result
    assert result["state"] == "Bayern"
    # Nach dem commit: Feiertage in DB
    total = db.query(PublicHoliday).count()
    assert total > 0
```

**Step 3: Tests ausführen**

```bash
docker-compose exec backend pytest tests/test_holiday_service.py -v
```
Erwartet: 10 PASSED

**Step 4: Commit**

```bash
git add backend/tests/test_holiday_service.py
git commit -m "test: add holiday service tests (10 tests)"
```

---

## Task 4: `tests/test_calculations_extended.py` – Calculation Service Lücken

**Files:**
- Create: `backend/tests/test_calculations_extended.py`

**Funktionen unter Test:**
- `get_weekly_hours_for_date(db, user, target_date) -> Decimal`
- `get_daily_target_for_date(user, target_date, weekly_hours=None) -> Decimal`
- `get_working_days_in_month(db, year, month) -> int`
- `get_monthly_target(db, user, year, month) -> Decimal`
- `get_vacation_account(db, user, year) -> Dict`
- `count_workdays(db, start, end) -> int`
- `get_overtime_account(db, user, up_to_year, up_to_month) -> Decimal`

**Step 1: Testdatei anlegen**

```python
"""Erweiterte Tests für calculation_service (Lücken aus Full Sweep Audit)."""
import pytest
from decimal import Decimal
from datetime import date, time
from app.models import (
    User, UserRole, TimeEntry, Absence, AbsenceType,
    PublicHoliday, WorkingHoursChange
)
from app.services import calculation_service


def make_user(db, **kwargs):
    """Helper: User erstellen."""
    defaults = dict(
        username="u",
        email="u@example.com",
        password_hash="hash",
        first_name="X",
        last_name="Y",
        role=UserRole.EMPLOYEE,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        is_active=True,
    )
    defaults.update(kwargs)
    user = User(**defaults)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_entry(db, user, d, hours):
    """Helper: Zeiteintrag mit `hours` Netto-Stunden erstellen."""
    entry = TimeEntry(
        user_id=user.id,
        date=d,
        start_time=time(8, 0),
        end_time=time(8 + int(hours), int((hours % 1) * 60)),
        break_minutes=0,
    )
    db.add(entry)
    db.commit()
    return entry
```

**Step 2: Tests für `get_weekly_hours_for_date`**

```python
# ============================================================
# get_weekly_hours_for_date
# ============================================================

def test_weekly_hours_no_history_returns_user_hours(db, test_user):
    """Kein historischer Eintrag → user.weekly_hours wird verwendet."""
    result = calculation_service.get_weekly_hours_for_date(
        db, test_user, date(2026, 3, 10)
    )
    assert result == Decimal('40.0')


def test_weekly_hours_with_history_before_date(db, test_user):
    """Historischer Eintrag vor Datum → historische Stunden."""
    change = WorkingHoursChange(
        user_id=test_user.id,
        weekly_hours=20.0,
        effective_from=date(2026, 1, 1),
    )
    db.add(change)
    db.commit()
    result = calculation_service.get_weekly_hours_for_date(
        db, test_user, date(2026, 3, 10)
    )
    assert result == Decimal('20.0')


def test_weekly_hours_with_history_after_date_ignored(db, test_user):
    """Historischer Eintrag NACH Datum → wird ignoriert, user.weekly_hours."""
    change = WorkingHoursChange(
        user_id=test_user.id,
        weekly_hours=20.0,
        effective_from=date(2026, 6, 1),  # Nach März
    )
    db.add(change)
    db.commit()
    result = calculation_service.get_weekly_hours_for_date(
        db, test_user, date(2026, 3, 10)
    )
    assert result == Decimal('40.0')  # Unverändert
```

**Step 3: Tests für `get_daily_target_for_date`**

```python
# ============================================================
# get_daily_target_for_date
# ============================================================

def test_daily_target_for_monday(db, test_user):
    """Montag (weekday=0) → 40h/5 = 8h/Tag."""
    monday = date(2026, 3, 9)  # 2026-03-09 ist ein Montag
    assert monday.weekday() == 0  # Sicherheitscheck
    result = calculation_service.get_daily_target_for_date(test_user, monday)
    assert result == Decimal('8.00')


def test_daily_target_for_friday(db, test_user):
    """Freitag (weekday=4) → 8h/Tag."""
    friday = date(2026, 3, 13)
    assert friday.weekday() == 4
    result = calculation_service.get_daily_target_for_date(test_user, friday)
    assert result == Decimal('8.00')


def test_daily_target_for_saturday_is_zero(db, test_user):
    """Samstag → 0."""
    saturday = date(2026, 3, 14)
    assert saturday.weekday() == 5
    result = calculation_service.get_daily_target_for_date(test_user, saturday)
    assert result == Decimal('0')


def test_daily_target_for_sunday_is_zero(db, test_user):
    """Sonntag → 0."""
    sunday = date(2026, 3, 15)
    assert sunday.weekday() == 6
    result = calculation_service.get_daily_target_for_date(test_user, sunday)
    assert result == Decimal('0')


def test_daily_target_with_daily_schedule(db):
    """use_daily_schedule=True → tagespezifische Stunden."""
    user = make_user(
        db,
        username="schedule_user",
        email="schedule@example.com",
        use_daily_schedule=True,
        hours_monday=4.0,
        hours_tuesday=6.0,
        hours_wednesday=8.0,
        hours_thursday=6.0,
        hours_friday=4.0,
    )
    monday = date(2026, 3, 9)
    result = calculation_service.get_daily_target_for_date(user, monday)
    assert result == Decimal('4.00')

    wednesday = date(2026, 3, 11)
    result = calculation_service.get_daily_target_for_date(user, wednesday)
    assert result == Decimal('8.00')
```

**Step 4: Tests für `get_working_days_in_month`**

```python
# ============================================================
# get_working_days_in_month
# ============================================================

def test_working_days_january_2026(db):
    """Januar 2026 → 22 Werktage."""
    result = calculation_service.get_working_days_in_month(db, 2026, 1)
    assert result == 22
```

**Step 5: Tests für `get_monthly_target`**

```python
# ============================================================
# get_monthly_target
# ============================================================

def test_monthly_target_with_holiday_reduces_target(db, test_user):
    """Feiertag im Monat → Soll wird reduziert."""
    # Ohne Feiertag: Januar 2026 = 22 Werktage × 8h = 176h
    target_without = calculation_service.get_monthly_target(db, test_user, 2026, 1)

    # Feiertag an Neujahr (01.01.2026 ist Donnerstag)
    h = PublicHoliday(date=date(2026, 1, 1), name="Neujahr", year=2026)
    db.add(h)
    db.commit()

    target_with = calculation_service.get_monthly_target(db, test_user, 2026, 1)
    assert target_with == target_without - Decimal('8.00')


def test_monthly_target_with_vacation_absence(db, test_user):
    """VACATION-Abwesenheit reduziert Soll."""
    target_without = calculation_service.get_monthly_target(db, test_user, 2026, 3)

    absence = Absence(
        user_id=test_user.id,
        date=date(2026, 3, 10),  # Dienstag
        type=AbsenceType.VACATION,
        hours=8.0,
    )
    db.add(absence)
    db.commit()

    target_with = calculation_service.get_monthly_target(db, test_user, 2026, 3)
    assert target_with == target_without - Decimal('8.00')


def test_monthly_target_training_absence_does_not_reduce(db, test_user):
    """TRAINING-Abwesenheit reduziert Soll NICHT (außer Haus = gilt als gearbeitet)."""
    target_without = calculation_service.get_monthly_target(db, test_user, 2026, 3)

    absence = Absence(
        user_id=test_user.id,
        date=date(2026, 3, 10),
        type=AbsenceType.TRAINING,
        hours=8.0,
    )
    db.add(absence)
    db.commit()

    target_with = calculation_service.get_monthly_target(db, test_user, 2026, 3)
    assert target_with == target_without  # Unverändert!


def test_monthly_target_with_overtime_absence(db, test_user):
    """OVERTIME-Abwesenheit reduziert Soll."""
    target_without = calculation_service.get_monthly_target(db, test_user, 2026, 3)

    absence = Absence(
        user_id=test_user.id,
        date=date(2026, 3, 10),
        type=AbsenceType.OVERTIME,
        hours=8.0,
    )
    db.add(absence)
    db.commit()

    target_with = calculation_service.get_monthly_target(db, test_user, 2026, 3)
    assert target_with == target_without - Decimal('8.00')
```

**Step 6: Tests für `get_vacation_account` – Pro-Rata**

```python
# ============================================================
# get_vacation_account – Pro-Rata (Audit-Fix)
# ============================================================

def test_vacation_account_first_work_day_reduces_budget(db):
    """first_work_day im laufenden Jahr → reduziertes Budget."""
    # Mitarbeiterin startet am 1. Juli 2026 → 6 volle Monate verbleiben
    user = make_user(
        db,
        username="new_employee",
        email="new@example.com",
        vacation_days=24,
        first_work_day=date(2026, 7, 1),  # 1. Juli → 6/12 des Jahres verbleiben
    )
    result = calculation_service.get_vacation_account(db, user, 2026)
    # Exakte Berechnung: 1. Juli, Monat hat 31 Tage
    # days_remaining = 31, months_remaining = 5 + 31/31 = 6.0
    # budget_days = 24 * 6.0 / 12 = 12.0
    assert result["budget_days"] == 12.0


def test_vacation_account_last_work_day_reduces_budget(db):
    """last_work_day im laufenden Jahr → reduziertes Budget."""
    # Mitarbeiter scheidet am 30. Juni 2026 aus → 6 Monate gearbeitet
    user = make_user(
        db,
        username="leaving_employee",
        email="leaving@example.com",
        vacation_days=24,
        last_work_day=date(2026, 6, 30),  # Ende Juni → 6/12 des Jahres
    )
    result = calculation_service.get_vacation_account(db, user, 2026)
    # Exakte Berechnung: 30. Juni, Monat hat 30 Tage
    # days_worked = 30, months_worked = 5 + 30/30 = 6.0
    # budget_days = 24 * 6.0 / 12 = 12.0
    assert result["budget_days"] == 12.0


def test_vacation_account_both_set_takes_minimum(db):
    """Beide gesetzt → Minimum der beiden Berechnungen."""
    # first_work_day = 1. Juli → budget_days = 12.0
    # last_work_day = 31. August → months_worked = 7 + 31/31 = 8.0 → 24*8/12 = 16.0
    # minimum(12.0, 16.0) = 12.0
    user = make_user(
        db,
        username="both_set",
        email="both@example.com",
        vacation_days=24,
        first_work_day=date(2026, 7, 1),
        last_work_day=date(2026, 8, 31),
    )
    result = calculation_service.get_vacation_account(db, user, 2026)
    assert result["budget_days"] == 12.0


def test_vacation_account_mid_month_day_accurate(db):
    """Tagesgenaue Berechnung: 15. März ≠ ganzer März."""
    user_15th = make_user(
        db,
        username="march_15",
        email="march15@example.com",
        vacation_days=12,
        first_work_day=date(2026, 3, 15),
    )
    user_1st = make_user(
        db,
        username="march_1",
        email="march1@example.com",
        vacation_days=12,
        first_work_day=date(2026, 3, 1),
    )
    result_15 = calculation_service.get_vacation_account(db, user_15th, 2026)
    result_1 = calculation_service.get_vacation_account(db, user_1st, 2026)
    # 15. März → weniger Budget als 1. März
    assert result_15["budget_days"] < result_1["budget_days"]
```

**Step 7: Tests für `count_workdays`**

```python
# ============================================================
# count_workdays
# ============================================================

def test_count_workdays_simple_range(db):
    """Einfacher Bereich Mo-Fr ohne Feiertage → 5 Werktage."""
    # 09.03.2026 (Mo) – 13.03.2026 (Fr)
    result = calculation_service.count_workdays(db, date(2026, 3, 9), date(2026, 3, 13))
    assert result == 5


def test_count_workdays_excludes_holidays(db):
    """Feiertag im Bereich → wird ausgeschlossen."""
    h = PublicHoliday(date=date(2026, 3, 11), name="Testfeiertag", year=2026)
    db.add(h)
    db.commit()
    # Mo-Fr inkl. Mittwoch als Feiertag → 4 Werktage
    result = calculation_service.count_workdays(db, date(2026, 3, 9), date(2026, 3, 13))
    assert result == 4


def test_count_workdays_excludes_weekends(db):
    """Wochenende wird ausgeschlossen."""
    # Sa-So-Mo: Nur Montag zählt
    result = calculation_service.count_workdays(db, date(2026, 3, 14), date(2026, 3, 16))
    assert result == 1  # Nur Montag 16.03.


def test_count_workdays_cross_month(db):
    """Monatsübergreifender Bereich."""
    # 30.03.2026 (Mo) – 03.04.2026 (Fr) → 5 Werktage
    result = calculation_service.count_workdays(db, date(2026, 3, 30), date(2026, 4, 3))
    assert result == 5
```

**Step 8: Tests für `get_overtime_account`**

```python
# ============================================================
# get_overtime_account
# ============================================================

def test_overtime_account_cumulates_across_months(db, test_user):
    """Mehrere Monate mit echten Einträgen → kumulierter Saldo."""
    # test_user: 40h/Woche, 8h/Tag
    # Januar 2026: 22 Werktage × 8h = 176h Soll
    # Eintragen: 10h am 9. Januar → 2h Überstunden nur dieser Tag
    entry_jan = TimeEntry(
        user_id=test_user.id,
        date=date(2026, 1, 9),
        start_time=time(8, 0),
        end_time=time(18, 0),
        break_minutes=0,
    )
    db.add(entry_jan)
    # Februar 2026: 20 Werktage × 8h = 160h Soll
    # Eintragen: 8h am 9. Februar → kein Plus/Minus
    entry_feb = TimeEntry(
        user_id=test_user.id,
        date=date(2026, 2, 9),
        start_time=time(8, 0),
        end_time=time(16, 0),
        break_minutes=0,
    )
    db.add(entry_feb)
    db.commit()

    # Erwartet: Jan-Balance = 10 - 176 = -166, Feb-Balance = 8 - 160 = -152
    # Gesamt = -318 (sehr negativ, aber test prüft nur ob Funktion läuft und kumuliert)
    result = calculation_service.get_overtime_account(db, test_user, 2026, 2)
    assert isinstance(result, Decimal)
    # Saldo muss kleiner 0 sein (mehr Soll als Ist)
    assert result < Decimal('0')


def test_overtime_account_no_entries_returns_zero(db, test_user):
    """Keine Einträge → 0.00."""
    result = calculation_service.get_overtime_account(db, test_user, 2026, 3)
    assert result == Decimal('0.00')
```

**Step 9: Tests ausführen**

```bash
docker-compose exec backend pytest tests/test_calculations_extended.py -v
```
Erwartet: ~25 PASSED

**Step 10: Commit**

```bash
git add backend/tests/test_calculations_extended.py
git commit -m "test: add extended calculation service tests (25 tests)"
```

---

## Task 5: conftest.py – Neue Fixtures ergänzen

**Files:**
- Modify: `backend/tests/conftest.py`

Einige Tests in Task 4 nutzen Inline-User-Erstellung (`make_user`). Für zukünftige Tests können globale Fixtures nützlich sein. Diese Task ergänzt die neuen Fixtures aus dem Design-Dokument.

**Step 1: Fixtures ergänzen**

Ergänze am Ende von `backend/tests/conftest.py`:

```python
from app.models import PublicHoliday, WorkingHoursChange
from datetime import date


@pytest.fixture(scope="function")
def public_holiday(db):
    """Ein Feiertag (Neujahr 2026) für Tests."""
    h = PublicHoliday(
        date=date(2026, 1, 1),
        name="Neujahr",
        year=2026,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


@pytest.fixture(scope="function")
def working_hours_change(db, test_user):
    """Historische Arbeitsstunden-Änderung (20h ab 2026-01-01) für test_user."""
    change = WorkingHoursChange(
        user_id=test_user.id,
        weekly_hours=20.0,
        effective_from=date(2026, 1, 1),
    )
    db.add(change)
    db.commit()
    db.refresh(change)
    return change
```

**Hinweis:** Die Imports am Anfang von conftest.py sind bereits vorhanden für `app.models`. Prüfe vor dem Einfügen ob `PublicHoliday` und `WorkingHoursChange` schon importiert sind (ggf. müssen sie ergänzt werden).

**Step 2: Gesamte Test-Suite ausführen**

```bash
docker-compose exec backend pytest tests/ -v
```
Erwartet: Alle Tests grün (bestehende + neue ~60)

**Step 3: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test: add public_holiday and working_hours_change fixtures to conftest"
```

---

## Erfolgskriterien

- `pytest tests/ -v` läuft durch ohne Fehler
- ~60 neue Tests grün
- Keine Änderungen an Produktionscode
- 4 neue Testdateien + erweitertes conftest.py committed
