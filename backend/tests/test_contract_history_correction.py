"""Teil A, Task 6: eine Änderung auf dem Datum der FRÜHESTEN Verlaufszeile
ersetzt diese an Ort und Stelle (id und effective_from bleiben); auf späteren
Zeilen bleibt „existiert bereits"."""
from datetime import date
from decimal import Decimal

import pytest

from app.models import WorkingHoursChange
from app.services import calculation_service as cs
from tests.test_contract_history_write import client, rows_of, url, explicit_contract, TODAY  # noqa: F401
from tests.wh_change_helpers import add_row

BASE = date(2020, 1, 1)
LATER = date(2026, 11, 1)


def _history(db, user):
    base = add_row(db, user, BASE, weekly_hours=40, **explicit_contract(vacation_days=Decimal("24")))
    later = add_row(db, user, LATER, weekly_hours=40, **explicit_contract(vacation_days=Decimal("30")))
    return base.id, later.id


def body(eff: str, **extra) -> dict:
    return {"effective_from": eff, "weekly_hours": 40, "work_days_per_week": 5, **extra}


def test_change_at_earliest_row_date_replaces_it(db, test_user, client):
    baseline_id, _ = _history(db, test_user)
    r = client.post(url(test_user), json=body("2020-01-01", vacation_days=28, note="Korrektur"))
    assert r.status_code == 201, r.text
    rows = rows_of(db, test_user)
    assert len(rows) == 2
    assert float(rows[0].vacation_days) == 28.0 and rows[0].id == baseline_id
    assert rows[0].effective_from == BASE and rows[0].note == "Korrektur"
    assert cs.vacation_entitlement_days(db, test_user, 2025) == Decimal("28.0")


def test_same_date_on_later_row_still_400(db, test_user, client):
    _history(db, test_user)
    r = client.post(url(test_user), json=body("2026-11-01", vacation_days=28))
    assert r.status_code == 400
    assert "Eine Stundenänderung für den 01.11.2026 existiert bereits" in r.text
    assert len(rows_of(db, test_user)) == 2


def test_preview_at_earliest_row_has_no_blocked_reason(db, test_user, client):
    _history(db, test_user)
    r = client.post(url(test_user) + "/preview", json=body("2020-01-01", vacation_days=28))
    assert r.status_code == 200, r.text
    assert r.json()["blocked_reason"] is None
    later = client.post(url(test_user) + "/preview", json=body("2026-11-01", vacation_days=28))
    assert "existiert bereits" in later.json()["blocked_reason"]
    assert len(rows_of(db, test_user)) == 2          # Vorschau schreibt nie
    assert float(rows_of(db, test_user)[0].vacation_days) == 24.0


@pytest.mark.xfail(strict=True, reason="Task 7: Verkürzungsgrund vacation_entitlement")
def test_correction_writes_summary_row_and_requires_reason_when_shortening(db, test_user, client):
    _history(db, test_user)
    no_reason = client.post(url(test_user), json=body("2020-01-01", vacation_days=20))
    assert no_reason.status_code == 400, no_reason.text
    ok = client.post(url(test_user), json=body(
        "2020-01-01", vacation_days=20, retroactive_reason_type="erfassungsfehler",
        retroactive_reason_text="Anspruch falsch erfasst", wage_risk_confirmed=True))
    assert ok.status_code == 201, ok.text
