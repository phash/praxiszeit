"""Gesamtreview 1.20 (B2, Punkt 2): die Antragsprüfung kennt das AKTUELLE
wirksame Ende des Zieleintrags (``entry_end_time``).

Der Server wertet bei der Genehmigung ein beantragtes Ende auch dann als Echo,
wenn es genau auf das aktuelle wirksame Ende fällt (``end_is_correction``) —
beim automatisch geschlossenen Eintrag lehnt er „genehmigen und anerkennen"
dann mit 400 ab (``lacks_actual_end``). Die Prüfung kannte bisher nur das
wirksame Ende zum Zeitpunkt des Antrags (``original_end_time``) und bot den
Knopf nach einer Neukappung trotzdem an.
"""
from datetime import time

from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.services import credit_override_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week

# Mo 08–12 + 15–17 → Hülle bis 17:15.
SHORTER_END = block_week(mon=[("08:00", "12:00"), ("15:00", "17:00")])


def _entry(db, user, start, end, **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON,
                  start_time=start, end_time=end, break_minutes=0, **kw)
    db.add(e)
    db.commit()
    return e


def _cr(db, user, entry, end, original_end):
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id, entry_kind="time_entry",
        request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
        time_entry_id=entry.id, proposed_date=MON, proposed_start_time=entry.start_time,
        proposed_end_time=end, proposed_break_minutes=0,
        original_date=MON, original_start_time=entry.start_time,
        original_end_time=original_end, original_break_minutes=0,
        reason="Ende nachgetragen")
    db.add(cr)
    db.commit()
    return cr


def _auto_closed_after_reclamp(db, user):
    """Automatisch geschlossen, damals bis 18:15 angerechnet, seit einer
    Neukappung (kürzere Hülle) bis 17:15 — Rohende 23:59 ist kein Stempel."""
    user.work_blocks = SHORTER_END
    return _entry(db, user, time(15, 0), time(17, 15), raw_end_time=time(23, 59),
                  auto_closed=True, clamp_grace_minutes=15)


def test_response_carries_current_effective_end(_db_session, employee_user, admin_client):
    e = _auto_closed_after_reclamp(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, e, end=time(17, 15), original_end=time(18, 15))
    body = admin_client.get(f"/api/admin/change-requests/{cr.id}").json()
    assert (body["entry_end_time"], body["entry_auto_closed"]) == ("17:15:00", True)
    assert body["original_end_time"] == "18:15:00"
    # Der Stempel bleibt verborgen (P18) — das wirksame Ende ist keiner.
    assert body["entry_raw_end_time"] is None


def test_list_carries_current_effective_end(_db_session, employee_user, admin_client):
    """Die Prüfliste (Batch-Enricher) trägt das Feld ebenso; ohne Kappung ist
    das wirksame Ende das gespeicherte."""
    employee_user.work_blocks = K_BLOCKS
    e = _entry(_db_session, employee_user, time(8, 0), time(16, 30))
    _cr(_db_session, employee_user, e, end=time(16, 0), original_end=time(16, 30))
    rows = admin_client.get("/api/admin/change-requests?status=pending").json()
    assert [r["entry_end_time"] for r in rows] == ["16:30:00"]


def test_proposed_end_on_current_effective_end_cannot_be_granted(_db_session, employee_user,
                                                                  admin_client):
    """Der Fall, den die Prüfung jetzt erkennt: das beantragte Ende 17:15 ist
    nicht das damalige (18:15), aber das aktuelle wirksame Ende — der Server
    lehnt „genehmigen und anerkennen" ab, der Antrag bleibt offen."""
    e = _auto_closed_after_reclamp(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, e, end=time(17, 15), original_end=time(18, 15))
    r = admin_client.post(f"/api/admin/change-requests/{cr.id}/review",
                          json={"action": "approve", "grant_credit_override": True})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == credit_override_service.AUTO_CLOSED_DETAIL
    _db_session.refresh(cr)
    assert cr.status == ChangeRequestStatus.PENDING
