"""Spec 14/P20: Dashboard-Hinweis aus den Sammelzeilen der letzten 30 Tage —
bei jeder Änderung (auch „ab heute", zukunftsdatiert, Löschung, Rücksetzung),
nur eigene Zeilen, nie Präfix oder Freitext des Grundes (P12)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import TimeEntry, TimeEntryAuditLog, User, UserRole
from app.services import reclamp_audit as ra
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app
from tests.wh_change_helpers import ANNA_WEEK, MONDAYS, RETRO_REASON, add_row, admin_client, entry, freeze, t
from tests.work_blocks_fixtures import block_week

NOW = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)
SHORT = block_week(mon=[("08:00", "12:00"), ("15:00", "17:00")], tue=[("08:00", "12:00")], thu=[("08:00", "12:00")])
SHORT_TEXT = "Mo 08:00–12:00 + 15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00"


def _summary_row(db, user, admin, note, *, created, entry_dates=False):
    row = TimeEntryAuditLog(
        time_entry_id=None, user_id=user.id, changed_by=admin.id, action="update", source="wh_reclamp",
        new_note=note, tenant_id=DEFAULT_TENANT_ID, created_at=created,
        old_date=date(2026, 9, 14) if entry_dates else None, new_date=date(2026, 9, 14) if entry_dates else None,
    )
    db.add(row)
    db.commit()
    return row


def _note(**kw):
    base = dict(effective_from=date(2026, 9, 1), deleted=False, count=0, delta_minutes=0, saldo_delta_minutes=0,
                skipped={}, grace=15, credit_reductions=0, reset_of=None, shortening=False, reason_type=None,
                reason_text_value=None, contract_before="a", contract_after="b")
    base.update(kw)
    return ra.summary_note(**base)


@pytest.fixture
def anna(db, test_user, monkeypatch):
    freeze(monkeypatch)
    add_row(db, test_user, date(2026, 9, 1), week=SHORT)
    return test_user


def test_past_change_with_counts_saldo_and_reason_label(db, anna, test_admin):
    _summary_row(db, anna, test_admin, _note(count=3, delta_minutes=-135, saldo_delta_minutes=-225,
                                             shortening=True, reason_type="erfassungsfehler",
                                             reason_text_value="Geheimer Freitext Reha"),
                 created=NOW - timedelta(days=2))
    [notice] = ra.schedule_change_notices(db, anna, now=NOW)
    assert notice["kind"] == "change"
    assert notice["text"] == (
        "Ihre Arbeitszeit wurde ab 01.09.2026 geändert (neu: Mo 08:00–12:00 + 15:00–17:00 / Di 08:00–12:00 / "
        "Do 08:00–12:00). 3 Einträge neu berechnet, angerechnete Zeit −2:15 h. Überstundenkonto im Zeitraum "
        "−3:45 h. Rückwirkende Verkürzung – Grund: Arbeitszeit war falsch hinterlegt (Fehlerkorrektur).")
    assert "[Erfassungsfehler korrigiert]" not in notice["text"] and "Reha" not in notice["text"]


def test_saldo_addition_without_reclamped_entries(db, anna, test_admin):
    """Spec 14: Neukappungs-Zusatz nur bei n > 0, Saldo-Zusatz nur bei Saldo Δ ≠ 0 —
    beide Bedingungen sind unabhängig. Nach PR3 häufigster Verkürzungsfall: eine
    rückwirkende reine Soll-Änderung ohne neu gekappten Eintrag (10.2, Beispielzeile 5)."""
    _summary_row(db, anna, test_admin, _note(count=0, saldo_delta_minutes=-240, credit_reductions=1,
                                             shortening=True, reason_type="sonstiges",
                                             reason_text_value="Freitext"),
                 created=NOW - timedelta(days=1))
    [notice] = ra.schedule_change_notices(db, anna, now=NOW)
    assert notice["text"] == (
        f"Ihre Arbeitszeit wurde ab 01.09.2026 geändert (neu: {SHORT_TEXT}). Überstundenkonto im Zeitraum "
        "−4:00 h. Rückwirkende Verkürzung – Grund: Sonstiges.")
    assert "neu berechnet" not in notice["text"] and "Freitext" not in notice["text"]


def test_reclamp_addition_without_saldo_change(db, anna, test_admin):
    """Gegenstück: n > 0 bei Saldo Δ = 0 → Neukappungs-Zusatz (auch „+0:00 h"),
    kein Satz zum Überstundenkonto."""
    _summary_row(db, anna, test_admin, _note(count=2, delta_minutes=0, saldo_delta_minutes=0),
                 created=NOW - timedelta(days=1))
    [notice] = ra.schedule_change_notices(db, anna, now=NOW)
    assert notice["text"] == (
        f"Ihre Arbeitszeit wurde ab 01.09.2026 geändert (neu: {SHORT_TEXT}). 2 Einträge neu berechnet, "
        "angerechnete Zeit +0:00 h.")
    assert "Überstundenkonto" not in notice["text"]


def test_future_reset_and_delete_texts(db, anna, test_admin):
    add_row(db, anna, date(2026, 11, 2), weekly_hours=25)
    _summary_row(db, anna, test_admin, _note(effective_from=date(2026, 11, 2)), created=NOW - timedelta(days=3))
    _summary_row(db, anna, test_admin, _note(effective_from=date(2026, 10, 8), reset_of=date(2026, 9, 1)),
                 created=NOW - timedelta(days=2))
    _summary_row(db, anna, test_admin, _note(deleted=True, count=1, delta_minutes=15, saldo_delta_minutes=15),
                 created=NOW - timedelta(days=1))
    texts = [n["text"] for n in ra.schedule_change_notices(db, anna, now=NOW)]
    assert texts == [
        "Die Arbeitszeit-Änderung ab 01.09.2026 wurde zurückgenommen. 1 Eintrag neu berechnet, angerechnete Zeit "
        "+0:15 h. Überstundenkonto im Zeitraum +0:15 h.",
        "Die Arbeitszeit-Änderung ab 01.09.2026 wurde ab 08.10.2026 auf den vorherigen Stand zurückgesetzt "
        "(neu: Mo 08:00–12:00 + 15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00).",
        "Ihre Arbeitszeit ändert sich ab 02.11.2026 (neu: 25,0 h/Woche (gleichmäßig, 5 Tage)).",
    ]


def test_future_reset_uses_the_future_tense(db, anna, test_admin):
    _summary_row(db, anna, test_admin, _note(effective_from=date(2026, 10, 12), reset_of=date(2026, 9, 1)),
                 created=NOW - timedelta(hours=1))
    [notice] = ra.schedule_change_notices(db, anna, now=NOW)
    assert notice["text"].startswith("Die Arbeitszeit-Änderung ab 01.09.2026 wird ab 12.10.2026 auf den vorherigen Stand")
    assert notice["kind"] == "reset"


def test_only_own_recent_parseable_summary_rows(db, anna, test_admin):
    other = User(username="kollegin", email="k@x.de", password_hash="h", first_name="K", last_name="T",
                 role=UserRole.EMPLOYEE, weekly_hours=40, work_days_per_week=5, vacation_days=30,
                 tenant_id=DEFAULT_TENANT_ID)
    db.add(other)
    db.commit()
    _summary_row(db, anna, test_admin, _note(), created=NOW - timedelta(days=31))                 # zu alt
    _summary_row(db, other, test_admin, _note(), created=NOW - timedelta(days=1))                 # fremd
    _summary_row(db, anna, test_admin, "angerechnet 2:15 h — Arbeitszeit-Änderung ab 01.09.2026",
                 created=NOW - timedelta(days=1), entry_dates=True)                               # Einzelzeile, Eintrag gelöscht
    _summary_row(db, anna, test_admin, "kein Format", created=NOW - timedelta(days=1))           # nicht lesbar
    _summary_row(db, anna, test_admin, _note(), created=NOW - timedelta(days=29))                 # zählt
    assert len(ra.schedule_change_notices(db, anna, now=NOW)) == 1


def test_dashboard_endpoint_shows_a_change_made_today(db, test_user, test_admin, monkeypatch):
    """P20: auch eine Änderung „ab heute" ohne Neukappung erzeugt einen Hinweis."""
    freeze(monkeypatch)
    add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
    admin = admin_client(db, test_admin)
    assert admin.post(f"/api/admin/users/{test_user.id}/working-hours-changes",
                      json={"effective_from": "2026-10-08", "blocks": SHORT}).status_code == 201
    test_app.dependency_overrides.clear()
    employee = admin_client(db, test_user)   # get_current_user → die Person selbst
    body = employee.get("/api/dashboard/").json()
    test_app.dependency_overrides.clear()
    assert [n["text"] for n in body["schedule_change_notices"]] == [
        "Ihre Arbeitszeit wurde ab 08.10.2026 geändert (neu: Mo 08:00–12:00 + 15:00–17:00 / Di 08:00–12:00 / "
        "Do 08:00–12:00)."]


def test_notice_stays_after_the_reclamped_entry_is_deleted(db, test_user, test_admin, monkeypatch):
    """Spec 14: Eintrag nach der Neukappung löschen → Hinweis bleibt. Auf
    PostgreSQL setzt das Löschen ``time_entry_id`` der Einzelzeile auf NULL
    (``ON DELETE SET NULL``); die SQLite-Suite läuft ohne Fremdschlüssel und
    bildet das hier nach. Die verwaiste Einzelzeile wird kein zweiter Hinweis
    und verdrängt die Sammelzeile nicht."""
    freeze(monkeypatch)
    add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
    monday = entry(db, test_user, MONDAYS[2], t(15), t(18))
    admin = admin_client(db, test_admin)
    resp = admin.post(f"/api/admin/users/{test_user.id}/working-hours-changes",
                      json={"effective_from": "2026-09-01", "blocks": SHORT, **RETRO_REASON})
    test_app.dependency_overrides.clear()
    assert resp.status_code == 201, resp.text

    before = ra.schedule_change_notices(db, test_user)
    for row in db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.time_entry_id == monday.id).all():
        row.time_entry_id = None
    db.delete(db.query(TimeEntry).filter(TimeEntry.id == monday.id).one())
    db.commit()
    after = ra.schedule_change_notices(db, test_user)

    assert [n["text"] for n in after] == [n["text"] for n in before]
    [notice] = after
    assert notice["text"].startswith(f"Ihre Arbeitszeit wurde ab 01.09.2026 geändert (neu: {SHORT_TEXT}). "
                                     "1 Eintrag neu berechnet, angerechnete Zeit −0:45 h.")
    assert notice["text"].endswith(" Rückwirkende Verkürzung – Grund: Arbeitszeit war falsch hinterlegt "
                                   "(Fehlerkorrektur).")
    assert RETRO_REASON["retroactive_reason_text"] not in notice["text"]
