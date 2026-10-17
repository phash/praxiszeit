"""Gesamtreview 1.20, Bündel B1 (Punkt 4, Nachzug): Änderungsantrag ohne
Zeitänderung an einem anerkannten Eintrag.

Punkt 4 hat die harten §3/§4-Prüfungen in beiden Bearbeiten-Routen für
Bearbeitungen ohne Zeitänderung ausgesetzt. Der dritte Schreibpfad — der
Änderungsantrag (Stellen in ``change_requests.create_change_request``,
Genehmigung in ``admin_change_requests.review_change_request``, C-1) — prüfte
weiter hart. Ausgerechnet den Weg, auf den der 409 der MA-Route verweist
(„… bitte per Änderungsantrag“), konnten Mitarbeitende damit nicht gehen: ein
Antrag, der an einem anerkannten Eintrag 07:00–19:00 ohne Pause nur die Notiz
ändert, scheiterte beim Stellen an §4 (400) und bei der Genehmigung an §3
(422). Jetzt gilt dieselbe Regel wie beim Bearbeiten: ändert der Antrag nichts,
was §3/§4 rechnen (Datum, angerechneter Beginn/Ende, Pause, nicht angerechnete
Minuten), bleiben die harten Prüfungen aus — außer es kommt eine Begründung
mit. Wer Zeiten oder Pause ändert, wird weiter hart geprüft.
"""
from datetime import time

import pytest

from app.middleware.auth import get_current_user, require_admin
from app.models import ChangeRequest, TimeEntry
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.models.system_setting import SystemSetting
from app.services.break_validation_service import BREAK_EXCEPTION_DISABLED_HINT
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
    endpoints_app,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON


def _recognized(db, user, end=time(19)):
    """Anerkannt 07:00–19:00 ohne Pause: 12 h (§3) und keine §4-Pause."""
    user.work_blocks = K_BLOCKS
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON, start_time=time(7),
                  end_time=end, break_minutes=0, uncredited_minutes=0, credit_override=True,
                  clamp_grace_minutes=15, note="alt")
    db.add(e)
    db.commit()
    return e


def _request(client, entry, end="19:00", **kw):
    body = {
        "request_type": "update",
        "time_entry_id": str(entry.id),
        "proposed_date": MON.isoformat(),
        "proposed_start_time": "07:00",
        "proposed_end_time": end,
        "proposed_break_minutes": 0,
        "proposed_note": "Hausbesuch",
        "reason": "Notiz ergänzt",
    }
    body.update(kw)
    return client.post("/api/change-requests/", json=body)


def _stored_cr(db, user, entry, end=time(19), **kw):
    """Antrag direkt gespeichert — prüft die Genehmigung unabhängig vom Stellen."""
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id, entry_kind="time_entry",
        request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
        time_entry_id=entry.id, proposed_date=MON, proposed_start_time=time(7),
        proposed_end_time=end, proposed_break_minutes=kw.pop("break_minutes", 0),
        proposed_note="Hausbesuch", reason="Notiz ergänzt",
        original_date=entry.date, original_start_time=entry.start_time,
        original_end_time=entry.end_time, original_break_minutes=entry.break_minutes,
        original_note=entry.note, original_uncredited_minutes=entry.uncredited_minutes, **kw)
    db.add(cr)
    db.commit()
    return cr


def _approve(client, cr):
    return client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})


def _switch_to(admin):
    """Antrag als MA gestellt, jetzt als Admin genehmigen — beide Client-Fixtures
    zugleich teilen sich die Überschreibungen derselben App (das zuletzt
    erzeugte gewinnt)."""
    endpoints_app.dependency_overrides[get_current_user] = lambda: admin
    endpoints_app.dependency_overrides[require_admin] = lambda: admin


# ── Stellen ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("end", ["19:00", "16:30"], ids=["12h-§3+§4", "9.5h-§4"])
def test_note_only_request_on_a_recognized_entry_is_accepted(_db_session, employee_user,
                                                             employee_client, end):
    h, m = map(int, end.split(":"))
    e = _recognized(_db_session, employee_user, end=time(h, m))
    r = _request(employee_client, e, end=end)
    assert r.status_code == 201, r.text
    cr = _db_session.query(ChangeRequest).one()
    assert (cr.proposed_note, cr.break_waiver_reason) == ("Hausbesuch", None)


def test_request_with_changed_break_is_still_checked_hard(_db_session, employee_user,
                                                          employee_client):
    """Kontrolle: 07:00–19:00 mit 45 Min. Pause = 11:15 h > 10 h (§3)."""
    e = _recognized(_db_session, employee_user)
    r = _request(employee_client, e, proposed_break_minutes=45)
    assert r.status_code == 422, r.text
    assert _db_session.query(ChangeRequest).count() == 0


def test_request_with_changed_end_is_still_checked_hard(_db_session, employee_user,
                                                        employee_client):
    """Kontrolle: ein anderes Ende ist eine Zeitänderung (§4 ohne Begründung)."""
    e = _recognized(_db_session, employee_user, end=time(16, 30))
    r = _request(employee_client, e, end="16:45")
    assert r.status_code == 400, r.text
    assert _db_session.query(ChangeRequest).count() == 0


def test_unchanged_request_with_a_reason_still_documents_the_exception(
        _db_session, employee_user, employee_client, admin_user):
    """Kontrolle: kommt eine Begründung mit, bleibt §4 eine Prüfung — die
    Ausnahme wird am Antrag gespeichert und bei der Genehmigung dokumentiert."""
    e = _recognized(_db_session, employee_user, end=time(16, 30))
    r = _request(employee_client, e, end="16:30", break_waiver_reason="Notfall")
    assert r.status_code == 201, r.text
    cr = _db_session.query(ChangeRequest).one()
    assert cr.break_waiver_reason == "Notfall"
    _switch_to(admin_user)
    r = _approve(employee_client, cr)
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.break_waiver_reason, e.note, e.credit_override) == ("Notfall", "Hausbesuch", True)


# ── Genehmigen ──────────────────────────────────────────────────────────────

def test_approving_a_note_only_request_keeps_the_recognition(_db_session, employee_user,
                                                             employee_client, admin_user):
    e = _recognized(_db_session, employee_user)
    r = _request(employee_client, e)
    assert r.status_code == 201, r.text
    cr = _db_session.query(ChangeRequest).one()
    _switch_to(admin_user)
    r = _approve(employee_client, cr)
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.start_time, e.end_time, e.break_minutes, e.note, e.credit_override) == (
        time(7), time(19), 0, "Hausbesuch", True)


@pytest.mark.parametrize("end", [time(19), time(16, 30)], ids=["12h-§3+§4", "9.5h-§4"])
def test_approval_of_a_stored_unchanged_request(_db_session, employee_user, admin_client, end):
    e = _recognized(_db_session, employee_user, end=end)
    cr = _stored_cr(_db_session, employee_user, e, end=end)
    r = _approve(admin_client, cr)
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.end_time, e.note, e.credit_override) == (end, "Hausbesuch", True)


def test_approval_does_not_repeat_the_unchanged_break_finding(_db_session, employee_user,
                                                              admin_client):
    """P14 wie in den Bearbeiten-Routen: ein unverändert bestehender §4-Befund
    wird nicht als ``PRESENCE_BREAK`` erneut gemeldet."""
    e = _recognized(_db_session, employee_user)
    cr = _stored_cr(_db_session, employee_user, e)
    r = _approve(admin_client, cr)
    assert r.status_code == 200, r.text
    assert not any(w.startswith("PRESENCE_BREAK") for w in r.json()["warnings"]), \
        r.json()["warnings"]


def test_approval_with_changed_break_is_still_checked_hard(_db_session, employee_user,
                                                           admin_client):
    """Kontrolle: ein gespeicherter Antrag mit geänderter Pause → 422 (§3),
    Eintrag unverändert, Antrag bleibt offen."""
    e = _recognized(_db_session, employee_user)
    cr = _stored_cr(_db_session, employee_user, e, break_minutes=45)
    r = _approve(admin_client, cr)
    assert r.status_code == 422, r.text
    _db_session.rollback()
    _db_session.refresh(e)
    _db_session.refresh(cr)
    assert (e.break_minutes, e.note, cr.status) == (0, "alt", ChangeRequestStatus.PENDING)


def test_approval_after_the_exception_was_switched_off(_db_session, employee_user, admin_client):
    """Kontrolle (#499, wie die Bearbeiten-Routen): trägt der Antrag eine
    Begründung, die der Mandant inzwischen nicht mehr zulässt, prüft die
    Genehmigung §4 weiter — 422 mit dem Hinweis auf den abgeschalteten Schalter."""
    e = _recognized(_db_session, employee_user, end=time(16, 30))
    cr = _stored_cr(_db_session, employee_user, e, end=time(16, 30),
                    break_waiver_reason="Notfall")
    _db_session.add(SystemSetting(key="break_exception_allowed", tenant_id=DEFAULT_TENANT_ID,
                                  value="false", description="break_exception_allowed"))
    _db_session.commit()
    r = _approve(admin_client, cr)
    assert r.status_code == 422, r.text
    assert BREAK_EXCEPTION_DISABLED_HINT in r.json()["detail"]
