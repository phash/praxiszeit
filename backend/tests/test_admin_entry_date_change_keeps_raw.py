"""Release-Review 1.18.2: eine reine DATUMS-Änderung durch den Admin darf den
Rohstempel weder überschreiben noch die bereits gekappte Zeit ein zweites Mal
kappen.

``admin_update_time_entry`` fütterte ``work_window_service.clamp`` mit dem
GESPEICHERTEN (also bereits gekappten) ``entry.start_time``. Bei einem PUT, das nur
``date`` schickt, gilt der Eintrag trotzdem als zeitbetroffen (``_times_affected``)
und die raw-Felder werden neu geschrieben — der echte Stempel wanderte damit auf
den gekappten Wert und die angerechnete Zeit rutschte pro Datumsänderung weiter
ins Soll-Fenster hinein.

Warum das mehr als Kosmetik ist: ``raw_start_time``/``raw_end_time`` sind der
§16-Nachweis der tatsächlichen Anwesenheit UND laut CLAUDE.md die Grundlage der
§5-Ruhezeitprüfung (``rest_time_service`` liest ``raw_end_time or end_time``).
Nach einer Datumskorrektur rechnete § 5 also gegen die geschönte Zeit.
"""
from datetime import date, time, timedelta

import pytest

from app.models import User, UserRole, TimeEntry
from app.routers.admin_time_entries import admin_update_time_entry
from app.schemas.time_entry import TimeEntryUpdate
from tests.conftest import DEFAULT_TENANT_ID


def _next_weekday(target_weekday: int) -> date:
    """Ein Datum in der Zukunft mit dem gewünschten Wochentag (0 = Montag)."""
    d = date.today() + timedelta(days=7)
    while d.weekday() != target_weekday:
        d += timedelta(days=1)
    return d


@pytest.fixture
def admin(db, default_tenant):
    u = User(
        username="adm_raw", email="adm_raw@t.de", password_hash="h",
        first_name="A", last_name="D", role=UserRole.ADMIN, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def employee(db, default_tenant):
    # Soll-Fenster: Montag 08:00–16:00, Dienstag 10:00–18:00.
    u = User(
        username="emp_raw", email="emp_raw@t.de", password_hash="h",
        first_name="E", last_name="M", role=UserRole.EMPLOYEE, weekly_hours=40.0,
        vacation_days=30, work_days_per_week=5, is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
        scheduled_start_monday=time(8, 0), scheduled_end_monday=time(16, 0),
        scheduled_start_tuesday=time(10, 0), scheduled_end_tuesday=time(18, 0),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_date_only_change_keeps_the_raw_stamp(db, default_tenant, admin, employee):
    monday, tuesday = _next_weekday(0), _next_weekday(1)
    # Mitarbeiter war ab 06:00 da; das Montags-Fenster (08:00, Puffer 15 min)
    # kappte die Anrechnung auf 07:45, der Rohstempel hielt die 06:00 fest.
    entry = TimeEntry(
        user_id=employee.id, tenant_id=DEFAULT_TENANT_ID, date=monday,
        start_time=time(7, 45), end_time=time(16, 15),
        raw_start_time=time(6, 0), raw_end_time=time(18, 30),
        break_minutes=30,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    # Der Admin korrigiert NUR das Datum (Eintrag gehörte auf den Dienstag).
    admin_update_time_entry(
        str(entry.id), TimeEntryUpdate(date=tuesday), db=db, current_user=admin,
    )
    db.refresh(entry)

    assert entry.date == tuesday
    # Der echte Stempel bleibt der echte Stempel.
    assert entry.raw_start_time == time(6, 0)
    assert entry.raw_end_time == time(18, 30)
    # Angerechnet wird nach dem Fenster des NEUEN Tages (Di 10:00–18:00, 15 min
    # Puffer) — gekappt aus dem Rohstempel, nicht aus der schon gekappten Zeit.
    assert entry.start_time == time(9, 45)
    assert entry.end_time == time(18, 15)


def test_repeated_date_changes_do_not_walk_the_time_inward(db, default_tenant, admin, employee):
    # Doppelkappung war kumulativ: jede weitere Datumsänderung schob die
    # angerechnete Zeit ein Stück weiter ins Fenster und fror sie als „Rohwert" ein.
    monday, tuesday = _next_weekday(0), _next_weekday(1)
    entry = TimeEntry(
        user_id=employee.id, tenant_id=DEFAULT_TENANT_ID, date=monday,
        start_time=time(7, 45), end_time=time(16, 15),
        raw_start_time=time(6, 0), raw_end_time=time(18, 30),
        break_minutes=30,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    for target in (tuesday, monday, tuesday):
        admin_update_time_entry(
            str(entry.id), TimeEntryUpdate(date=target), db=db, current_user=admin,
        )
        db.refresh(entry)

    assert entry.raw_start_time == time(6, 0)
    assert entry.raw_end_time == time(18, 30)
    assert entry.start_time == time(9, 45)
    assert entry.end_time == time(18, 15)


def test_explicit_time_change_still_sets_the_new_raw_stamp(db, default_tenant, admin, employee):
    # Gegenprobe: schickt der Admin eine neue Zeit mit, ist SIE der neue
    # Rohstempel — der alte darf nicht konserviert werden.
    monday = _next_weekday(0)
    entry = TimeEntry(
        user_id=employee.id, tenant_id=DEFAULT_TENANT_ID, date=monday,
        start_time=time(7, 45), end_time=time(16, 15),
        raw_start_time=time(6, 0), raw_end_time=time(18, 30),
        break_minutes=30,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    admin_update_time_entry(
        str(entry.id), TimeEntryUpdate(start_time=time(6, 30)), db=db, current_user=admin,
    )
    db.refresh(entry)

    assert entry.raw_start_time == time(6, 30)
    assert entry.start_time == time(7, 45)
