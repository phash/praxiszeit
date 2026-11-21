"""Plan 2026-11-21 Task 1: ``is_baseline`` in der Verlaufsantwort.

Die automatisch erfasste Ausgangszeile (``reclamp_audit.BASELINE_ROW_NOTE``)
trägt ``is_baseline = True``; jede andere Zeile ``False``. Überschreibt die
Verwaltung die Ausgangszeile (Änderung mit gleichem Wirkungsdatum), ist sie eine
gewöhnliche Zeile und verliert die Kennzeichnung."""
from datetime import date

import pytest

from app.models import User
from app.services import reclamp_audit, work_blocks_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app
from tests.wh_change_helpers import admin_client, changes_url, freeze
from tests.work_blocks_fixtures import block_week

FIRST_WORK_DAY = date(2026, 10, 1)
_FOUR = [("08:00", "12:00")]
FULL_WEEK = block_week(mon=_FOUR, tue=_FOUR, wed=_FOUR, thu=_FOUR, fri=_FOUR)
MON_TUE = block_week(mon=_FOUR, tue=_FOUR)


@pytest.fixture
def client(db, test_admin, monkeypatch):
    freeze(monkeypatch, date(2026, 11, 19))
    yield admin_client(db, test_admin)
    test_app.dependency_overrides.clear()


@pytest.fixture
def person(db):
    targets = work_blocks_service.derive_targets(FULL_WEEK)
    user = User(username="aushilfe", email="aushilfe@x.de", password_hash="h", first_name="A", last_name="H",
                vacation_days=30, is_active=True, tenant_id=DEFAULT_TENANT_ID,
                first_work_day=FIRST_WORK_DAY, work_blocks=FULL_WEEK, **targets)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _flags(client, user) -> dict:
    r = client.get(changes_url(user))
    assert r.status_code == 200, r.text
    return {row["effective_from"]: row["is_baseline"] for row in r.json()}


def test_baseline_row_flagged_in_listing(client, person):
    r = client.post(changes_url(person), json={"effective_from": "2026-11-20", "blocks": MON_TUE})
    assert r.status_code == 201, r.text
    assert r.json()["is_baseline"] is False
    assert _flags(client, person) == {"2026-10-01": True, "2026-11-20": False}


def test_replaced_baseline_loses_flag(client, person):
    assert client.post(changes_url(person), json={"effective_from": "2026-11-20", "blocks": MON_TUE}).status_code == 201
    r = client.post(changes_url(person), json={"effective_from": "2026-10-01", "blocks": MON_TUE})
    assert r.status_code == 201, r.text
    assert _flags(client, person) == {"2026-10-01": False, "2026-11-20": False}


def test_constant_lives_in_reclamp_audit():
    from app.routers import admin_users
    assert reclamp_audit.BASELINE_ROW_NOTE == "Automatisch erfasster Ausgangswert vor der ersten Stundenänderung"
    assert admin_users.BASELINE_ROW_NOTE is reclamp_audit.BASELINE_ROW_NOTE
