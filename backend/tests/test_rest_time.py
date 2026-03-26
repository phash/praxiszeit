"""Tests für ArbZG §5 Ruhezeitvalidierung."""
from datetime import date, time
from app.models import TimeEntry
from app.services.rest_time_service import check_rest_time_violations
from tests.conftest import DEFAULT_TENANT_ID


def _make_entry(db, user, d, start_h, start_m, end_h, end_m):
    """Helper: Zeiteintrag erstellen und committen."""
    entry = TimeEntry(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=d,
        start_time=time(start_h, start_m),
        end_time=time(end_h, end_m),
        break_minutes=0,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def test_no_entries_no_violations(db, test_user):
    """Keine Einträge → keine Verstöße."""
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert violations == []


def test_sufficient_rest_no_violation(db, test_user):
    """>11h Ruhezeit → kein Verstoß."""
    _make_entry(db, test_user, date(2026, 3, 10), 8, 0, 17, 0)   # Ende 17:00
    _make_entry(db, test_user, date(2026, 3, 11), 8, 0, 17, 0)   # Start 08:00 → 15h Ruhe
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert violations == []


def test_insufficient_rest_creates_violation(db, test_user):
    """<11h Ruhezeit → Verstoß mit korrekten Feldern."""
    _make_entry(db, test_user, date(2026, 3, 10), 8, 0, 22, 0)   # Ende 22:00
    _make_entry(db, test_user, date(2026, 3, 11), 7, 0, 15, 0)   # Start 07:00 → nur 9h Ruhe
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert len(violations) == 1
    v = violations[0]
    assert v["day1_date"] == "2026-03-10"
    assert v["day2_date"] == "2026-03-11"
    assert v["actual_rest_hours"] == 9.0
    assert v["min_rest_hours"] == 11
    assert v["deficit_hours"] == 2.0
    assert v["day1_end"] == "22:00:00"
    assert v["day2_start"] == "07:00:00"


def test_violation_fields_are_complete(db, test_user):
    """Violation-Dict enthält alle erwarteten Felder."""
    _make_entry(db, test_user, date(2026, 3, 10), 14, 0, 23, 0)
    _make_entry(db, test_user, date(2026, 3, 11), 8, 0, 16, 0)
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert len(violations) == 1
    v = violations[0]
    for key in ("day1_date", "day1_end", "day2_date", "day2_start", "actual_rest_hours", "min_rest_hours", "deficit_hours"):
        assert key in v, f"Missing key: {key}"


def test_split_shifts_no_false_positive(db, test_user):
    """Split Shifts (mehrere Einträge gleicher Tag) → kein False Positive."""
    # Tag 1: 08:00-12:00 + 14:00-18:00 (intra-day Gap soll NICHT als Verstoß zählen)
    _make_entry(db, test_user, date(2026, 3, 10), 8, 0, 12, 0)
    _make_entry(db, test_user, date(2026, 3, 10), 14, 0, 18, 0)
    # Tag 2: 08:00–16:00 → Ruhezeit von Ende Tag 1 (18:00) bis Start Tag 2 (08:00) = 14h ✓
    _make_entry(db, test_user, date(2026, 3, 11), 8, 0, 16, 0)
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert violations == []


def test_multiple_violations_in_month(db, test_user):
    """Mehrere Verstöße im Monat werden alle erfasst."""
    _make_entry(db, test_user, date(2026, 3, 10), 8, 0, 22, 0)
    _make_entry(db, test_user, date(2026, 3, 11), 7, 0, 15, 0)
    _make_entry(db, test_user, date(2026, 3, 20), 8, 0, 22, 0)
    _make_entry(db, test_user, date(2026, 3, 21), 7, 0, 15, 0)
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert len(violations) == 2
    dates = {v["day1_date"] for v in violations}
    assert "2026-03-10" in dates
    assert "2026-03-20" in dates


def test_month_filter_excludes_other_months(db, test_user):
    """Monatsfilter: Nur gefilterte Monate werden geprüft (kein Cross-Month)."""
    # Verstoß zwischen Feb 28 und Mar 1 – nur im März filtern
    _make_entry(db, test_user, date(2026, 2, 28), 8, 0, 22, 0)
    _make_entry(db, test_user, date(2026, 3, 1), 7, 0, 15, 0)
    # Nur März geprüft → Feb-Eintrag nicht im Filter → kein Vortag für März-Eintrag
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert len(violations) == 0


def test_no_month_filter_checks_full_year(db, test_user):
    """Ohne Monatsfilter: ganzes Jahr wird geprüft (Cross-Month Verstoß sichtbar)."""
    _make_entry(db, test_user, date(2026, 2, 28), 8, 0, 22, 0)
    _make_entry(db, test_user, date(2026, 3, 1), 7, 0, 15, 0)
    violations = check_rest_time_violations(db, test_user, 2026)  # kein month-Filter
    assert len(violations) == 1


def test_custom_min_rest_hours(db, test_user):
    """Custom min_rest_hours Parameter wird respektiert."""
    _make_entry(db, test_user, date(2026, 3, 10), 8, 0, 17, 0)   # Ende 17:00
    _make_entry(db, test_user, date(2026, 3, 11), 8, 0, 17, 0)   # Start 08:00 → 15h Ruhe
    # Standard 11h → kein Verstoß
    assert check_rest_time_violations(db, test_user, 2026, month=3) == []
    # Custom 16h → Verstoß (15h < 16h)
    violations = check_rest_time_violations(db, test_user, 2026, month=3, min_rest_hours=16)
    assert len(violations) == 1
    assert violations[0]["min_rest_hours"] == 16


def test_single_entry_no_violation(db, test_user):
    """Einzelner Eintrag (kein Vortag vorhanden) → kein Verstoß."""
    _make_entry(db, test_user, date(2026, 3, 15), 8, 0, 17, 0)
    violations = check_rest_time_violations(db, test_user, 2026, month=3)
    assert violations == []
