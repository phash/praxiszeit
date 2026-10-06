"""#486: Die Sammel-Genehmigung reicht die Warnungen jedes Antrags durch.

``bulk-review`` ruft je Antrag ``review_change_request`` auf, verwarf aber den
Rueckgabewert — und damit die Warnungen (Kappung #462, §6 Nacht, §3 Woche,
Kind-krank-Limit). Wer zehn Antraege auf einmal genehmigte, erfuhr von keiner.
"""
from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import ChangeRequest, ChangeRequestStatus, ChangeRequestType
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

MON = date(2026, 6, 1)


@pytest.fixture
def admin_client(db, test_admin):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: test_admin
    test_app.dependency_overrides[require_admin] = lambda: test_admin
    yield TestClient(test_app)
    test_app.dependency_overrides.clear()


def _cr(db, user, start, end, d=MON):
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id,
        request_type=ChangeRequestType.CREATE, entry_kind="time_entry",
        status=ChangeRequestStatus.PENDING, proposed_date=d,
        proposed_start_time=start, proposed_end_time=end,
        proposed_break_minutes=30, reason="nachgetragen",
    )
    db.add(cr)
    db.commit()
    return cr


def test_bulk_approve_returns_each_items_warnings(admin_client, db, test_user):
    test_user.scheduled_start_monday = time(8, 0)
    test_user.scheduled_end_monday = time(17, 0)
    db.commit()
    clamped = _cr(db, test_user, time(7, 0), time(16, 0))
    plain = _cr(db, test_user, time(9, 0), time(12, 0), d=date(2026, 6, 2))

    r = admin_client.post("/api/admin/change-requests/bulk-review", json={
        "request_ids": [str(clamped.id), str(plain.id)], "action": "approve",
    })
    assert r.status_code == 200, r.text
    items = {i["request_id"]: i for i in r.json()["items"]}
    assert items[str(clamped.id)]["status"] == "approved"
    assert any(w.startswith("WORK_WINDOW_CLAMPED") for w in items[str(clamped.id)]["warnings"])
    assert items[str(plain.id)]["warnings"] == []


def test_failed_item_has_no_warnings(admin_client, db, test_user):
    cr = _cr(db, test_user, time(9, 0), time(12, 0))
    cr.status = ChangeRequestStatus.APPROVED
    db.commit()
    r = admin_client.post("/api/admin/change-requests/bulk-review", json={
        "request_ids": [str(cr.id)], "action": "approve",
    })
    item = r.json()["items"][0]
    assert item["status"] == "failed"
    assert item["warnings"] == []
