"""Spec 2026-10-08, 13.3 / P3 / P4 (PR2): „Anerkennen" — Felder, Protokoll,
weiche Warnungen, Dauerhaftigkeit."""
import uuid
from datetime import time

import app.routers.time_entries as te
from app.models import TimeEntry, TimeEntryAuditLog
from app.models.tenant import Tenant
from app.services import credit_override_service as cos
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON


def _entry(db, user, start, end, **kw):
    e = TimeEntry(tenant_id=kw.pop("tenant_id", DEFAULT_TENANT_ID), user_id=user.id,
                  date=kw.pop("day", MON), start_time=start, end_time=end,
                  break_minutes=kw.pop("break_minutes", 0), **kw)
    db.add(e)
    db.commit()
    return e


def _k7(db, user):
    """K7 wie nach PR1 gespeichert: 07:00–19:00 gestempelt, 07:45–18:15 angerechnet."""
    user.work_blocks = K_BLOCKS
    return _entry(db, user, time(7, 45), time(18, 15), raw_start_time=time(7),
                  raw_end_time=time(19), uncredited_minutes=150, clamp_grace_minutes=15)


def _post(client, entry):
    return client.post(f"/api/admin/time-entries/{entry.id}/credit-override")


def _override_logs(db):
    return db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.source == cos.CREDIT_OVERRIDE_SOURCE).all()


def _codes(r):
    return [w.split(":", 1)[0] for w in r.json()["warnings"]]


def test_source_marker_fits_varchar_40():
    """``time_entry_audit_logs.source`` ist varchar(40) (Migration 037) — SQLite
    ignoriert die Länge, PostgreSQL wirft 500."""
    assert cos.CREDIT_OVERRIDE_SOURCE == "credit_override"
    assert len(cos.CREDIT_OVERRIDE_SOURCE) <= 40


def test_sets_fields_and_writes_one_audit_row(_db_session, employee_user, admin_user, admin_client):
    e = _k7(_db_session, employee_user)
    r = _post(admin_client, e)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["start_time"], body["end_time"]) == ("07:00:00", "19:00:00")
    assert (body["raw_start_time"], body["raw_end_time"]) == (None, None)
    assert (body["uncredited_minutes"], body["not_credited_minutes"]) == (0, 0)
    assert body["credit_override"] is True
    assert body["clamp_grace_minutes"] == 15     # 13.3 Schritt 4: bleibt unverändert
    assert body["net_hours"] == 12.0
    [log] = _override_logs(_db_session)
    assert (log.action, log.user_id, log.changed_by) == ("update", employee_user.id, admin_user.id)
    assert (log.old_start_time, log.old_end_time) == (time(7, 45), time(18, 15))
    assert (log.new_start_time, log.new_end_time) == (time(7), time(19))
    assert log.old_note == (
        "angerechnet 8:00 h, nicht angerechnet 4:00 h, davon 2:30 h zwischen den Blöcken")
    assert log.new_note == "angerechnet 12:00 h — von der Verwaltung anerkannt"
    assert log.row_hash   # #121: über die Objektschicht geschrieben


def test_is_idempotent(_db_session, employee_user, admin_client):
    e = _k7(_db_session, employee_user)
    assert _post(admin_client, e).status_code == 200
    r = _post(admin_client, e)
    assert (r.status_code, r.json()["warnings"]) == (200, [])
    assert len(_override_logs(_db_session)) == 1


def test_open_entry_is_400(_db_session, employee_user, admin_client):
    e = _entry(_db_session, employee_user, time(8), None)
    r = _post(admin_client, e)
    assert (r.status_code, r.json()["detail"]) == (400, cos.OPEN_ENTRY_DETAIL)
    assert cos.OPEN_ENTRY_DETAIL == (
        "Ein offener Eintrag kann erst nach dem Ausstempeln anerkannt werden.")


def test_auto_closed_entry_is_400(_db_session, employee_user, admin_client):
    """P18: 23:59 ist kein Stempel — Anerkennen öffnete sonst das Schlupfloch."""
    employee_user.work_blocks = K_BLOCKS
    e = _entry(_db_session, employee_user, time(8), time(18, 15), raw_end_time=time(23, 59),
               uncredited_minutes=150, auto_closed=True)
    r = _post(admin_client, e)
    assert (r.status_code, r.json()["detail"]) == (400, cos.AUTO_CLOSED_DETAIL)
    assert cos.AUTO_CLOSED_DETAIL == (
        "Automatisch geschlossener Eintrag: Bitte zuerst das tatsächliche Ende eintragen.")
    _db_session.refresh(e)
    assert (e.credit_override, e.end_time) == (False, time(18, 15))


def test_collision_at_the_raw_start_is_409(_db_session, employee_user, admin_client):
    e = _k7(_db_session, employee_user)
    _entry(_db_session, employee_user, time(7), time(7, 30))
    r = _post(admin_client, e)
    assert (r.status_code, r.json()["detail"]) == (
        409, "Ein anderer Eintrag an diesem Tag beginnt bereits um 07:00.")
    _db_session.refresh(e)
    assert e.credit_override is False
    assert _override_logs(_db_session) == []


def test_hard_limits_are_only_soft_warnings(_db_session, employee_user, admin_client):
    """P4: 12 h ohne Pause — Anerkennen blockiert nie an §3/§4."""
    r = _post(admin_client, _k7(_db_session, employee_user))
    assert r.status_code == 200
    assert _codes(r) == ["DAILY_HOURS_HARD", "BREAK_WARNING"]


def test_k10_gives_only_the_8h_warning(_db_session, employee_user, admin_client):
    """Spec 6.3 K10: 08:00–18:00, Pause 45, anerkannt → 9,25 h, DAILY_HOURS_WARNING."""
    employee_user.work_blocks = K_BLOCKS
    e = _entry(_db_session, employee_user, time(8), time(18), break_minutes=45,
               uncredited_minutes=150, clamp_grace_minutes=15)
    r = _post(admin_client, e)
    assert r.json()["net_hours"] == 9.25
    assert r.json()["warnings"] == ["DAILY_HOURS_WARNING"]


def test_exempt_person_gets_no_warnings(_db_session, employee_user, admin_client):
    """§18 (``exempt_from_arbzg``): keine ArbZG-Warnungen, auch nicht weich."""
    employee_user.exempt_from_arbzg = True
    r = _post(admin_client, _k7(_db_session, employee_user))
    assert (r.status_code, r.json()["warnings"]) == (200, [])


def test_unknown_entry_is_404(_db_session, employee_user, admin_client):
    r = admin_client.post(f"/api/admin/time-entries/{uuid.uuid4()}/credit-override")
    assert r.status_code == 404


def test_entry_of_another_tenant_is_404(_db_session, employee_user, admin_client):
    other = Tenant(id=uuid.uuid4(), name="Fremd", slug="fremd")
    _db_session.add(other)
    _db_session.commit()
    e = _entry(_db_session, employee_user, time(7, 45), time(18, 15), tenant_id=other.id,
               raw_start_time=time(7), uncredited_minutes=150)
    assert _post(admin_client, e).status_code == 404
    _db_session.refresh(e)
    assert e.credit_override is False


def test_employee_cannot_call_the_endpoint(_db_session, employee_user, employee_client):
    """``require_admin``: die Aktion gehört der Verwaltung (Mitarbeitende
    beantragen die Anrechnung, P21)."""
    e = _k7(_db_session, employee_user)
    r = _post(employee_client, e)
    assert r.status_code in (401, 403), r.text
    _db_session.refresh(e)
    assert e.credit_override is False


def test_admin_edit_keeps_the_recognition(_db_session, employee_user, admin_client):
    """P3: die Verwaltung bestätigt bei der Direktbearbeitung — das Flag bleibt.

    Gestempelt 07:30–17:30 mit 45 Min Pause (anerkannt 9,25 h): die Admin-
    Bearbeitung prüft §3/§4 weiterhin hart, deshalb ein zulässiger Tag."""
    employee_user.work_blocks = K_BLOCKS
    e = _entry(_db_session, employee_user, time(7, 45), time(17, 30), break_minutes=45,
               raw_start_time=time(7, 30), uncredited_minutes=150, clamp_grace_minutes=15)
    assert _post(admin_client, e).status_code == 200
    r = admin_client.put(f"/api/admin/time-entries/{e.id}", json={"note": "geprüft"})
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.credit_override, e.start_time, e.end_time, e.uncredited_minutes) == (
        True, time(7, 30), time(17, 30), 0)
    assert e.raw_start_time is None


def _recognized_today(db, user, monkeypatch):
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    user.work_blocks = K_BLOCKS
    return _entry(db, user, time(7), time(19), uncredited_minutes=0, credit_override=True)


def _delete_logs(db, entry):
    return db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.time_entry_id == entry.id, TimeEntryAuditLog.action == "delete").all()


def test_employee_delete_of_recognized_entry_is_409(_db_session, employee_user, employee_client,
                                                    monkeypatch):
    """P3 zu Ende gedacht (Sicherheitsprüfung SEC-PR1-ROLE-03): das MA-PUT auf
    einen anerkannten Eintrag ist gesperrt — ohne die Sperre am DELETE löschte
    die Person ihn heute und legte ihn neu an, und die neue Zeile wäre wieder
    gekappt: eine stille Rücknahme ohne Antrag, Protokoll der Verwaltung oder
    Vorschau (P11). Derselbe Weg wie beim Bearbeiten: per Änderungsantrag."""
    e = _recognized_today(_db_session, employee_user, monkeypatch)
    r = employee_client.delete(f"/api/time-entries/{e.id}")
    assert (r.status_code, r.json()["detail"]) == (
        409, "Anerkannter Eintrag – Änderung bitte per Änderungsantrag.")
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id) is not None
    assert _delete_logs(_db_session, e) == []


def test_admin_delete_of_recognized_entry_stays_allowed(_db_session, employee_user, admin_client,
                                                        monkeypatch):
    """Die Verwaltung bleibt Herrin des Eintrags (P3) — beide Löschrouten."""
    e = _recognized_today(_db_session, employee_user, monkeypatch)
    assert admin_client.delete(f"/api/admin/time-entries/{e.id}").status_code == 204
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id) is None

    e2 = _entry(_db_session, employee_user, time(7), time(19), credit_override=True)
    assert admin_client.delete(f"/api/time-entries/{e2.id}").status_code == 204
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e2.id) is None
