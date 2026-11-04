"""Teil A, Task 4: der Schreibweg der Arbeitszeit-Änderung (Anlegen, Vorschau,
Löschen, Rücksetzung) trägt die fünf Vertragsfelder — ``vacation_days``,
``track_hours``, ``milog_working_time_account``, ``agreed_monthly_hours``,
``use_fixed_monthly_target``.

Nicht gesendete Felder erben den Snapshot zum Wirkungsdatum, nie die User-Zeile;
ein ausdrücklich gesendetes ``agreed_monthly_hours: null`` heißt „abgeleitet"."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models import TimeEntry, User
from app.services import calculation_service as cs
from app.services import wh_change_service, work_blocks_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.wh_change_helpers import (
    ANNA_WEEK, RETRO_REASON, add_row, contract_client_fixture, changes_url as url, rows_of, explicit_contract, t,
)

TODAY = date(2026, 11, 3)
CONTRACT = ("vacation_days", "track_hours", "milog_working_time_account",
            "agreed_monthly_hours", "use_fixed_monthly_target")
NOT_NULL = ("vacation_days", "track_hours", "milog_working_time_account", "use_fixed_monthly_target")


client = pytest.fixture(name="client")(contract_client_fixture)


def schedule(*, blocks=None, block_pauses=None, **contract) -> cs.Schedule:
    values = explicit_contract(**contract)
    return cs.Schedule(
        weekly_hours=Decimal("15"), use_daily_schedule=True,
        day_hours=(Decimal("7"), Decimal("4"), None, Decimal("4"), None), work_days_per_week=3,
        blocks=blocks, block_pauses=block_pauses, **values,
    )


def test_pure_vacation_change_is_saveable_and_freezes_baseline(db, test_user, client):
    test_user.vacation_days = 24
    test_user.work_days_per_week = 4
    db.commit()
    r = client.post(url(test_user), json={"effective_from": "2026-11-01", "weekly_hours": float(test_user.weekly_hours),
                                          "work_days_per_week": 4, "vacation_days": 30})
    assert r.status_code == 201, r.text
    assert r.json()["vacation_days"] == 30.0
    rows = rows_of(db, test_user)
    assert [float(w.vacation_days) for w in rows] == [24.0, 30.0]          # Basis-Zeile friert 24 ein
    assert float(db.get(User, test_user.id).vacation_days) == 30.0          # Spiegel (eff ≤ heute)


def test_customer_case_end_to_end(db, test_user, client):
    """Spec A5: keine Zeilen, kein ``first_work_day``, keine Buchungen; 40 h an
    4 Tagen, Anspruch 24 → ab 01.11.2026 5 Tage und 30 Tage Anspruch."""
    test_user.vacation_days = 24
    test_user.work_days_per_week = 4
    db.commit()
    r = client.post(url(test_user), json={"effective_from": "2026-11-01", "weekly_hours": 40,
                                          "work_days_per_week": 5, "vacation_days": 30})
    assert r.status_code == 201, r.text
    db.expire_all()
    assert cs.vacation_entitlement_days(db, test_user, 2026) == Decimal("25.0")
    assert cs.vacation_entitlement_days(db, test_user, 2027) == Decimal("30.0")
    assert cs.vacation_entitlement_days(db, test_user, 2025) == Decimal("24.0")
    assert float(db.get(User, test_user.id).vacation_days) == 30.0


def test_omitted_fields_inherit_snapshot_not_user_row(db, test_user, client):
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, **explicit_contract(
        vacation_days=Decimal("24"), agreed_monthly_hours=Decimal("50.0")))
    test_user.vacation_days = 28              # Live-Zeile weicht ab — darf nicht durchschlagen
    test_user.agreed_monthly_hours = Decimal("80.0")
    db.commit()
    r = client.post(url(test_user), json={"effective_from": "2026-11-01", "weekly_hours": 38})
    assert r.status_code == 201, r.text
    new = rows_of(db, test_user)[-1]
    assert new.effective_from == date(2026, 11, 1)
    assert new.vacation_days == Decimal("24.0")
    assert new.agreed_monthly_hours == Decimal("50.0")
    assert (new.track_hours, new.milog_working_time_account, new.use_fixed_monthly_target) == (True, False, False)


def test_explicit_null_agreed_means_derived(db, test_user, client):
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, **explicit_contract(
        agreed_monthly_hours=Decimal("50.0")))
    test_user.agreed_monthly_hours = Decimal("50.0")
    db.commit()
    r = client.post(url(test_user), json={"effective_from": "2026-11-01", "weekly_hours": 40,
                                          "agreed_monthly_hours": None})
    assert r.status_code == 201, r.text
    assert rows_of(db, test_user)[-1].agreed_monthly_hours is None
    assert db.get(User, test_user.id).agreed_monthly_hours is None          # Spiegel schreibt auch None


def test_future_dated_change_not_mirrored(db, test_user, client):
    test_user.vacation_days = 24
    db.commit()
    r = client.post(url(test_user), json={"effective_from": "2027-01-01", "weekly_hours": 40,
                                          "vacation_days": 30})
    assert r.status_code == 201, r.text
    assert [float(w.vacation_days) for w in rows_of(db, test_user)] == [24.0, 30.0]
    assert float(db.get(User, test_user.id).vacation_days) == 24.0


def test_preview_snapshot_unchanged_false_for_contract_only_change(db, test_user, client, monkeypatch):
    calls = []
    real = wh_change_service.run_change

    def spy(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)
    monkeypatch.setattr(wh_change_service, "run_change", spy)
    body = {"effective_from": "2026-11-01", "weekly_hours": 40, "work_days_per_week": 5}
    same = client.post(url(test_user) + "/preview", json=body)
    assert same.status_code == 200, same.text
    assert calls == []                                    # unverändert → Kurzschluss
    changed = client.post(url(test_user) + "/preview", json={**body, "vacation_days": 24})
    assert changed.status_code == 200, changed.text
    assert changed.json()["blocked_reason"] is None
    assert calls == [1]                                   # reine Anspruchsänderung wird gerechnet
    assert rows_of(db, test_user) == []                   # Vorschau schreibt nie


def test_reset_body_in_block_mode_keeps_entitlement():
    parsed = work_blocks_service.parse_week_blocks(ANNA_WEEK)
    pred = schedule(blocks=parsed.blocks, block_pauses=parsed.pauses, vacation_days=Decimal("24"),
                    agreed_monthly_hours=Decimal("43.3"), milog_working_time_account=True)
    body = wh_change_service.reset_body(pred, date(2026, 12, 1), uuid4())
    assert "blocks" in body
    assert body["vacation_days"] == 24.0 and body["track_hours"] is True
    assert body["milog_working_time_account"] is True and body["use_fixed_monthly_target"] is False
    assert body["agreed_monthly_hours"] == 43.3


def test_reset_body_without_blocks_carries_none_agreed():
    body = wh_change_service.reset_body(schedule(), date(2026, 12, 1), uuid4())
    assert set(CONTRACT) <= body.keys()
    assert body["agreed_monthly_hours"] is None


def test_reset_matches_compares_contract_fields(db, test_user, client):
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, **explicit_contract(vacation_days=Decimal("24")))
    target = add_row(db, test_user, date(2026, 6, 1), weekly_hours=40,
                     **explicit_contract(vacation_days=Decimal("30")))
    pred = cs.get_schedule_for_date(db, test_user, date(2026, 5, 31))
    body = wh_change_service.reset_body(pred, date(2026, 7, 1), target.id)
    stale = client.post(url(test_user), json={**body, "vacation_days": 30})
    assert stale.status_code == 409, stale.text
    # Task 7: die Rücksetzung ab 01.07. (< heute) senkt den Anspruch 2026
    # rückwirkend (30 → 24) — Verkürzungsgrund ``vacation_entitlement``.
    ok = client.post(url(test_user), json={**body, **RETRO_REASON})
    assert ok.status_code == 201, ok.text
    assert rows_of(db, test_user)[-1].vacation_days == Decimal("24.0")


def test_delete_restores_mirror(db, test_user, client):
    add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, **explicit_contract(vacation_days=Decimal("24")))
    young = add_row(db, test_user, date(2026, 10, 1), weekly_hours=40,
                    **explicit_contract(vacation_days=Decimal("30"), track_hours=False))
    test_user.vacation_days = 30
    test_user.track_hours = False
    db.commit()
    # Task 7: das Löschen senkt den Anspruch 2026 rückwirkend — mit Schutzpaket.
    r = client.request("DELETE", f"{url(test_user)}/{young.id}", json=RETRO_REASON)
    assert r.status_code == 204, r.text
    user = db.get(User, test_user.id)
    assert float(user.vacation_days) == 24.0
    assert user.track_hours is True


@pytest.mark.usefixtures("no_contract_fill")
def test_write_paths_set_all_five_without_test_listener(db, test_user, test_admin, client):
    """Ohne den Test-Listener: jeder Produktionskonstruktor muss alle fünf Felder
    setzen — sonst scheiterten die vier NOT-NULL-Spalten laut (PG: HTTP 500)."""
    # Anlegen ohne Verlauf: Basis-Zeile + neue Zeile (Buchung → Deckung ab 01.02.).
    db.add(TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, date=date(2026, 2, 2),
                     start_time=t(8), end_time=t(12), break_minutes=0))
    db.commit()
    # Task 7: 30 → 28 ab 01.11. (< heute) senkt den Anspruch 2026 rückwirkend.
    r = client.post(url(test_user), json={"effective_from": "2026-11-01", "weekly_hours": 40, "vacation_days": 28,
                                          **RETRO_REASON})
    assert r.status_code == 201, r.text
    created_id = r.json()["id"]
    assert len(rows_of(db, test_user)) == 2

    # Lückenzeile: zweite Person, älteste Zeile nach dem Beginn (first_work_day).
    other = User(username="gap", email="gap@x.de", password_hash="h", first_name="G", last_name="P",
                 weekly_hours=40, vacation_days=30, work_days_per_week=5, is_active=True,
                 tenant_id=DEFAULT_TENANT_ID, first_work_day=date(2026, 1, 1))
    db.add(other)
    db.commit()
    add_row(db, other, date(2026, 6, 1), weekly_hours=40, **explicit_contract())
    r = client.post(url(other), json={"effective_from": "2026-10-01", "weekly_hours": 30})
    assert r.status_code == 201, r.text
    assert [w.effective_from for w in rows_of(db, other)] == [date(2026, 1, 1), date(2026, 6, 1), date(2026, 10, 1)]

    # Rücksetzung der neuen Zeile der ersten Person.
    pred = cs.get_schedule_for_date(db, test_user, date(2026, 10, 31))
    r = client.post(url(test_user), json=wh_change_service.reset_body(pred, date(2026, 11, 2), created_id))
    assert r.status_code == 201, r.text
    reset_id = r.json()["id"]

    # Löschen (jüngste Zeile) — Spiegel zurück auf die vorherige.
    r = client.request("DELETE", f"{url(test_user)}/{reset_id}", json=RETRO_REASON)
    assert r.status_code == 204, r.text

    rows = rows_of(db, test_user) + rows_of(db, other)
    assert len(rows) == 5
    for row in rows:
        for field in NOT_NULL:
            assert getattr(row, field) is not None, (row.effective_from, field)
    assert float(db.get(User, test_user.id).vacation_days) == 28.0
