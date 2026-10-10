"""Spec 2026-10-08, 13.3 / P3 / P4 (PR2): „Anerkennen" — Felder, Protokoll,
weiche Warnungen, Dauerhaftigkeit."""
import uuid
from datetime import time

import app.routers.time_entries as te
from app.models import Absence, AbsenceType, TimeEntry, TimeEntryAuditLog
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


def _recognized(db, user):
    user.work_blocks = K_BLOCKS
    return _entry(db, user, time(7), time(19), uncredited_minutes=0, credit_override=True)


def _sick(**kw):
    return {"date": MON.isoformat(), "type": "sick", "hours": 8, **kw}


def test_employee_absence_over_recognized_entry_is_409(_db_session, employee_user,
                                                       employee_client):
    """Parallelpfad zu DELETE (Review Task 5): ``create_absence`` löscht ohne
    ``keep_time_entries`` alle Einträge der gebuchten Tage — auch den
    anerkannten. Abwesenheit buchen, wieder löschen, Eintrag neu anlegen wäre
    sonst dieselbe stille Rücknahme ohne Antrag (P3/P11), und anders als das
    DELETE ohne Sperre auf heute."""
    e = _recognized(_db_session, employee_user)
    r = employee_client.post("/api/absences/", json=_sick())
    assert (r.status_code, r.json()["detail"]) == (
        409, "Anerkannter Eintrag – Änderung bitte per Änderungsantrag.")
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id) is not None
    assert _delete_logs(_db_session, e) == []
    assert _db_session.query(Absence).count() == 0


def test_employee_absence_keeping_entries_stays_allowed(_db_session, employee_user,
                                                        employee_client):
    """Mit ``keep_time_entries`` (Monatsjournal „+") bleibt der anerkannte
    Eintrag stehen — dort gibt es nichts zu sperren."""
    e = _recognized(_db_session, employee_user)
    r = employee_client.post("/api/absences/", json=_sick(keep_time_entries=True))
    assert r.status_code == 201, r.text
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id).credit_override is True


def test_admin_absence_over_recognized_entry_stays_allowed(_db_session, employee_user,
                                                           admin_client):
    """Die Verwaltung bleibt zuständig (P3): sie bucht und löscht dabei mit
    Protokoll wie bisher."""
    e = _recognized(_db_session, employee_user)
    r = admin_client.post("/api/absences/", json=_sick(user_id=str(employee_user.id)))
    assert r.status_code == 201, r.text
    _db_session.expire_all()
    assert _db_session.get(TimeEntry, e.id) is None
    [log] = _delete_logs(_db_session, e)
    assert log.source == "absence_creation"


# ── „Anrechnung beantragen" (P21) und „genehmigen und anerkennen" ──────────────
import pytest  # noqa: E402

from app.models import ChangeRequest  # noqa: E402
from app.models.change_request import ChangeRequestStatus, ChangeRequestType  # noqa: E402
from app.routers.admin_change_requests import GRANT_ONLY_UPDATE_DETAIL  # noqa: E402
from app.routers.change_requests import CREDIT_REQUEST_REJECTED_DETAIL  # noqa: E402


def _request(client, entry, **kw):
    body = {
        "request_type": kw.pop("request_type", "update"),
        "time_entry_id": str(entry.id) if entry is not None else None,
        "proposed_date": MON.isoformat(),
        "proposed_start_time": kw.pop("start", "07:00"),
        "proposed_end_time": kw.pop("end", "19:00"),
        "proposed_break_minutes": 0,
        "reason": "Habe in der Lücke Patienten versorgt",
        "request_credit_override": True,
    }
    body.update(kw)
    return client.post("/api/change-requests/", json=body)


def test_employee_can_request_credit(_db_session, employee_user, employee_client):
    e = _k7(_db_session, employee_user)
    r = _request(employee_client, e)
    assert r.status_code == 201, r.text
    assert r.json()["request_credit_override"] is True
    cr = _db_session.query(ChangeRequest).one()
    assert (cr.request_credit_override, cr.original_uncredited_minutes) == (True, 150)


def test_request_rejected_without_not_credited_time(_db_session, employee_user, employee_client):
    e = _entry(_db_session, employee_user, time(8), time(16), break_minutes=30)
    r = _request(employee_client, e, start="08:00", end="16:00")
    assert (r.status_code, r.json()["detail"]) == (400, CREDIT_REQUEST_REJECTED_DETAIL)


def test_request_rejected_for_recognized_entry_create_and_absence(_db_session, employee_user,
                                                                   employee_client):
    e = _k7(_db_session, employee_user)
    e.credit_override = True
    _db_session.commit()
    assert _request(employee_client, e).json()["detail"] == CREDIT_REQUEST_REJECTED_DETAIL
    r = _request(employee_client, None, request_type="create", start="08:00", end="12:00")
    assert (r.status_code, r.json()["detail"]) == (400, CREDIT_REQUEST_REJECTED_DETAIL)
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "create", "entry_kind": "absence", "proposed_date": MON.isoformat(),
        "proposed_absence_type": "sick", "proposed_absence_hours": 8, "reason": "krank",
        "request_credit_override": True,
    })
    assert (r.status_code, r.json()["detail"]) == (400, CREDIT_REQUEST_REJECTED_DETAIL)
    assert _db_session.query(ChangeRequest).count() == 0


def test_request_on_a_foreign_entry_is_404_like_an_unknown_id(_db_session, employee_user,
                                                               admin_user, employee_client):
    """Spec 11.4 nennt „fremd" in der 400-Zeile — die Eigentümerprüfung (#120)
    läuft aber vorher und antwortet wie bei einer unbekannten ID mit 404. Ein
    400 nur für fremde Einträge verriete deren Existenz (vgl. 7.1, Review N3)."""
    admin_user.work_blocks = K_BLOCKS
    foreign = _entry(_db_session, admin_user, time(7, 45), time(18, 15), raw_start_time=time(7),
                     raw_end_time=time(19), uncredited_minutes=150)
    r_foreign = _request(employee_client, foreign)
    r_unknown = _request(employee_client, None, time_entry_id=str(uuid.uuid4()))
    assert (r_foreign.status_code, r_foreign.json()) == (r_unknown.status_code, r_unknown.json())
    assert r_foreign.status_code == 404
    assert _db_session.query(ChangeRequest).count() == 0


def test_request_rejected_for_open_entry(_db_session, employee_user, employee_client):
    """Spec 11.4 „offen" (Review Task 6): ein offener K20-Eintrag hat schon
    gekappte Minuten am Anfang (``not_credited_minutes`` 45 > 0) — allein die
    Bedingung ``end_time is None`` hält ihn auf. Ohne sie liefe ein Antrag
    07:00–19:00 mit Kennzeichen durch und würde angelegt."""
    employee_user.work_blocks = K_BLOCKS
    e = _entry(_db_session, employee_user, time(7, 45), None, raw_start_time=time(7),
               clamp_grace_minutes=15)
    from app.services import work_window_service
    assert work_window_service.not_credited_minutes(e) == 45
    r = _request(employee_client, e)
    assert (r.status_code, r.json()["detail"]) == (400, CREDIT_REQUEST_REJECTED_DETAIL)
    assert _db_session.query(ChangeRequest).count() == 0


def test_request_rejected_for_delete(_db_session, employee_user, employee_client):
    """P21: Anrechnung beantragen gibt es nur als Änderung — ein Löschantrag
    mit Kennzeichen (K7, nicht angerechnete Zeit vorhanden) wird abgelehnt."""
    e = _k7(_db_session, employee_user)
    r = _request(employee_client, e, request_type="delete")
    assert (r.status_code, r.json()["detail"]) == (400, CREDIT_REQUEST_REJECTED_DETAIL)
    assert _db_session.query(ChangeRequest).count() == 0


# Review Focus 3: 18:15 (gekapptes Ende) und 23:59 liefen über unclamp_input wieder auf 23:59.
# Review Task 6 (PR2): minutengenau — die Schemata lassen Sekunden zu, ein
# exakter Vergleich ließ „23:59:30" (angezeigt „23:59") an der Sperre vorbei.
@pytest.mark.parametrize("end, status", [
    ("18:15", 400), ("23:59", 400), ("23:59:30", 400), ("18:15:30", 400), ("17:30", 201),
])
def test_auto_closed_needs_the_actual_end(_db_session, employee_user, employee_client, end, status):
    employee_user.work_blocks = K_BLOCKS
    e = _entry(_db_session, employee_user, time(8), time(18, 15), raw_end_time=time(23, 59),
               uncredited_minutes=150, auto_closed=True, clamp_grace_minutes=15)
    r = _request(employee_client, e, start="08:00", end=end)
    assert r.status_code == status, r.text
    if status == 400:
        assert r.json()["detail"] == cos.AUTO_CLOSED_DETAIL


import app.routers.change_requests as cr_router  # noqa: E402


def _today_is_mon(monkeypatch, hour=20):
    from datetime import datetime
    monkeypatch.setattr(cr_router, "today_local", lambda: MON)
    monkeypatch.setattr(cr_router, "now_local", lambda: datetime.combine(MON, time(hour)))


def test_request_for_todays_closed_entry_is_allowed(_db_session, employee_user, employee_client,
                                                    monkeypatch):
    """Gesamtreview PR2 (Fund 1): der Lückentext an clock_out/create/update —
    für Mitarbeitende immer der HEUTIGE Eintrag — verweist auf „Anrechnung
    beantragen". Spec 14 kennt keine Tagesgrenze: ein geschlossener Eintrag
    von heute ist beantragbar, solange das Datum bleibt."""
    _today_is_mon(monkeypatch)
    e = _k7(_db_session, employee_user)
    r = _request(employee_client, e)
    assert r.status_code == 201, r.text
    assert _db_session.query(ChangeRequest).one().request_credit_override is True


def test_todays_ordinary_update_request_stays_rejected(_db_session, employee_user,
                                                       employee_client, monkeypatch):
    """Nur die Anrechnung öffnet heute — eine gewöhnliche Änderung des
    heutigen Eintrags geht weiter direkt (Anträge nur für vergangene Tage)."""
    _today_is_mon(monkeypatch)
    e = _k7(_db_session, employee_user)
    r = _request(employee_client, e, request_credit_override=False)
    assert (r.status_code, r.json()["detail"]) == (
        400, "Änderungsanträge sind nur für vergangene Tage möglich")


def test_todays_request_with_an_end_in_the_future_is_rejected(_db_session, employee_user,
                                                              employee_client, monkeypatch):
    """Heute lässt das Anlegen ein späteres Ende zu — anerkannt würde dauerhaft
    (P11) eine Zeit, die noch gar nicht gearbeitet ist."""
    _today_is_mon(monkeypatch, hour=18)
    e = _k7(_db_session, employee_user)
    r = _request(employee_client, e)
    assert (r.status_code, r.json()["detail"]) == (400, cr_router.CREDIT_REQUEST_FUTURE_END_DETAIL)
    assert _db_session.query(ChangeRequest).count() == 0


@pytest.mark.parametrize("today", [False, True])
def test_credit_request_keeps_the_date_of_the_entry(_db_session, employee_user, employee_client,
                                                    monkeypatch, today):
    """Gesamtreview PR2 (Fund 3): Nicht-Anrechnung und Begründung gehören zum
    Tag des Eintrags — die Genehmigung kappte sonst gegen die Blöcke des
    Zieltags und erkennte die Zeiten dort an."""
    if today:
        _today_is_mon(monkeypatch)
    e = _k7(_db_session, employee_user)
    from datetime import timedelta
    r = _request(employee_client, e, proposed_date=(MON - timedelta(days=7)).isoformat())
    assert (r.status_code, r.json()["detail"]) == (400, CREDIT_REQUEST_REJECTED_DETAIL)
    assert _db_session.query(ChangeRequest).count() == 0


def _cr(db, user, entry, **kw):
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id, entry_kind="time_entry",
        request_type=kw.pop("request_type", ChangeRequestType.UPDATE),
        status=ChangeRequestStatus.PENDING,
        time_entry_id=entry.id if entry is not None else None,
        proposed_date=MON, proposed_start_time=kw.pop("start", time(7)),
        proposed_end_time=kw.pop("end", time(19)), proposed_break_minutes=0,
        reason="Habe in der Lücke Patienten versorgt", **kw)
    db.add(cr)
    db.commit()
    return cr


def _review(client, cr, **body):
    return client.post(f"/api/admin/change-requests/{cr.id}/review",
                       json={"action": "approve", **body})


def test_approving_a_credit_request_recognizes_the_entry(_db_session, employee_user, admin_client):
    e = _k7(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, e, request_credit_override=True,
             original_uncredited_minutes=150)
    r = _review(admin_client, cr)
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.credit_override, e.start_time, e.end_time, e.uncredited_minutes) == (
        True, time(7), time(19), 0)
    [log] = _override_logs(_db_session)
    assert log.new_note == (
        "angerechnet 12:00 h — auf Antrag der beschäftigten Person von der Verwaltung anerkannt")
    assert log.change_request_id == cr.id
    codes = _codes(r)
    assert "WORK_WINDOW_CLAMPED" not in codes   # jetzt ungekappt angerechnet
    assert "DAILY_HOURS_HARD" in codes          # P4: nur weich


def test_admin_can_decline_the_recognition(_db_session, employee_user, admin_client):
    e = _k7(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, e, request_credit_override=True)
    assert _review(admin_client, cr, grant_credit_override=False).status_code == 200
    _db_session.refresh(e)
    assert e.credit_override is False
    assert _override_logs(_db_session) == []


def test_approve_and_recognize_an_ordinary_update(_db_session, employee_user, admin_client):
    e = _k7(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, e)
    assert _review(admin_client, cr, grant_credit_override=True).status_code == 200
    [log] = _override_logs(_db_session)
    assert log.new_note == "angerechnet 12:00 h — von der Verwaltung anerkannt"


def test_grant_only_for_updates_and_cr_stays_pending(_db_session, employee_user, admin_client):
    cr = _cr(_db_session, employee_user, None, request_type=ChangeRequestType.CREATE,
             start=time(8), end=time(12))
    r = _review(admin_client, cr, grant_credit_override=True)
    assert (r.status_code, r.json()["detail"]) == (400, GRANT_ONLY_UPDATE_DETAIL)
    _db_session.refresh(cr)
    assert cr.status == ChangeRequestStatus.PENDING


@pytest.mark.parametrize("request_type", [ChangeRequestType.CREATE, ChangeRequestType.UPDATE])
def test_grant_rejected_for_absence_request(_db_session, employee_user, admin_client,
                                            request_type):
    """„genehmigen und anerkennen" nur an Zeiteinträgen (Review Task 6): auch
    ein Abwesenheits-UPDATE fällt unter ``entry_kind == "absence"``, nicht erst
    unter ``request_type``. Der Antrag bleibt offen, nichts wird gebucht."""
    absence = None
    if request_type == ChangeRequestType.UPDATE:
        absence = Absence(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                          type=AbsenceType.VACATION, hours=8)
        _db_session.add(absence)
        _db_session.commit()
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, entry_kind="absence",
        request_type=request_type, status=ChangeRequestStatus.PENDING,
        absence_id=absence.id if absence is not None else None,
        proposed_date=MON, proposed_absence_type="sick", proposed_absence_hours=8,
        reason="krank")
    _db_session.add(cr)
    _db_session.commit()
    r = _review(admin_client, cr, grant_credit_override=True)
    assert (r.status_code, r.json()["detail"]) == (400, GRANT_ONLY_UPDATE_DETAIL)
    _db_session.expire_all()
    assert _db_session.get(ChangeRequest, cr.id).status == ChangeRequestStatus.PENDING
    assert [(a.type.value, float(a.hours)) for a in _db_session.query(Absence).all()] == (
        [("vacation", 8.0)] if absence is not None else [])
    assert _override_logs(_db_session) == []


@pytest.mark.parametrize("raw_end, end", [
    (time(23, 59), time(18, 15)),
    (time(23, 59), time(23, 59)),
    # Nach einem Verschieben trägt der Eintrag kein Rohende 23:59 mehr —
    # ``end_is_correction`` hielte ein eingereichtes 23:59 dann für ein echtes
    # Ende, und Anerkennen rechnete 08:00–23:59 an.
    (None, time(23, 59)),
    # Review Task 6 (PR2): Sekunden ändern nichts — 23:59:30 ist dieselbe Minute.
    (time(23, 59), time(23, 59, 30)),
    (None, time(23, 59, 30)),
])
def test_grant_on_auto_closed_entry_needs_the_actual_end(_db_session, employee_user,
                                                         admin_client, raw_end, end):
    """P18/P21 an der Genehmigung: ein gewöhnlicher Antrag ohne tatsächliches
    Ende (gekapptes Ende 18:15 oder 23:59) + „genehmigen und anerkennen" würde
    das synthetische 23:59 anerkennen. Precondition VOR der Statusänderung —
    der Antrag bleibt offen, der Eintrag unverändert."""
    employee_user.work_blocks = K_BLOCKS
    e = _entry(_db_session, employee_user, time(8), time(18, 15), raw_end_time=raw_end,
               uncredited_minutes=150, auto_closed=True, clamp_grace_minutes=15)
    cr = _cr(_db_session, employee_user, e, start=time(8), end=end)
    r = _review(admin_client, cr, grant_credit_override=True)
    assert (r.status_code, r.json()["detail"]) == (400, cos.AUTO_CLOSED_DETAIL)
    _db_session.refresh(cr)
    _db_session.refresh(e)
    assert cr.status == ChangeRequestStatus.PENDING
    assert (e.credit_override, e.auto_closed, e.end_time) == (False, True, time(18, 15))
    assert _override_logs(_db_session) == []


def test_grant_on_auto_closed_entry_with_the_actual_end(_db_session, employee_user, admin_client):
    """Mit tatsächlichem Ende (17:30) hebt der UPDATE-Zweig ``auto_closed`` auf
    (``end_is_correction``), danach wird anerkannt: 08:00–17:30 = 9:30 h."""
    employee_user.work_blocks = K_BLOCKS
    e = _entry(_db_session, employee_user, time(8), time(18, 15), raw_end_time=time(23, 59),
               uncredited_minutes=150, auto_closed=True, clamp_grace_minutes=15)
    cr = _cr(_db_session, employee_user, e, start=time(8), end=time(17, 30),
             request_credit_override=True)
    r = _review(admin_client, cr)
    assert r.status_code == 200, r.text
    _db_session.refresh(e)
    assert (e.credit_override, e.auto_closed, e.start_time, e.end_time, e.uncredited_minutes) == (
        True, False, time(8), time(17, 30), 0)
    assert float(e.net_hours) == 9.5


def test_seconds_do_not_turn_the_synthetic_end_into_a_stamp(_db_session, employee_user,
                                                            admin_client):
    """Review Task 6 (PR2): ein gewöhnlicher Antrag mit „23:59:30" (in der
    Oberfläche „23:59") hob ``auto_closed`` auf — ``end_is_correction``
    verglich sekundengenau. Danach rechnete ein Anerkennen der Verwaltung bis
    23:59:30 an. Minutengenau ist es das synthetische 23:59: das Kennzeichen
    bleibt, das gespeicherte Paar unverändert, Anerkennen verlangt weiter das
    tatsächliche Ende."""
    employee_user.work_blocks = K_BLOCKS
    e = _entry(_db_session, employee_user, time(8), time(18, 15), raw_end_time=time(23, 59),
               uncredited_minutes=150, auto_closed=True, clamp_grace_minutes=15)
    cr = _cr(_db_session, employee_user, e, start=time(8), end=time(23, 59, 30))
    assert _review(admin_client, cr).status_code == 200
    _db_session.refresh(e)
    assert (e.auto_closed, e.end_time, e.raw_end_time) == (True, time(18, 15), time(23, 59))
    r = _post(admin_client, e)
    assert (r.status_code, r.json()["detail"]) == (400, cos.AUTO_CLOSED_DETAIL)
    _db_session.refresh(e)
    assert e.credit_override is False
    assert _override_logs(_db_session) == []


def test_bulk_approval_takes_the_request_value(_db_session, employee_user, admin_client):
    e = _k7(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, e, request_credit_override=True)
    r = admin_client.post("/api/admin/change-requests/bulk-review",
                          json={"request_ids": [str(cr.id)], "action": "approve"})
    assert r.status_code == 200 and r.json()["succeeded"] == 1, r.text
    _db_session.refresh(e)
    assert e.credit_override is True


def test_response_carries_entry_state_and_snapshot(_db_session, employee_user, admin_client):
    e = _k7(_db_session, employee_user)
    cr = _cr(_db_session, employee_user, e, request_credit_override=True,
             original_uncredited_minutes=150)
    body = admin_client.get(f"/api/admin/change-requests/{cr.id}").json()
    assert body["request_credit_override"] is True
    assert body["original_uncredited_minutes"] == 150
    assert (body["entry_credit_override"], body["entry_not_credited_minutes"],
            body["entry_auto_closed"]) == (False, 240, False)


def test_employee_list_loads_target_entries_in_one_query(_db_session, employee_user,
                                                        employee_client):
    """Review Task 6: die MA-Liste (``GET /api/change-requests/``, bis 500
    Anträge) reichert über den Batch-Enricher an — EIN Query für alle
    Zieleinträge wie in der Admin-Liste, nicht einer je Antrag."""
    from datetime import timedelta
    from sqlalchemy import event
    from tests.conftest import engine

    employee_user.work_blocks = K_BLOCKS
    for i in range(5):
        e = _entry(_db_session, employee_user, time(7, 45), time(18, 15), day=MON + timedelta(days=i),
                   raw_start_time=time(7), raw_end_time=time(19), uncredited_minutes=150)
        _cr(_db_session, employee_user, e, request_credit_override=True)

    count = {"n": 0}

    def _listener(conn, cursor, statement, parameters, context, executemany):
        if "from time_entries" in statement.lower():
            count["n"] += 1

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        r = employee_client.get("/api/change-requests/")
    finally:
        event.remove(engine, "before_cursor_execute", _listener)

    assert r.status_code == 200, r.text
    assert [x["entry_not_credited_minutes"] for x in r.json()] == [240] * 5
    assert count["n"] == 1, f"erwartet 1 Eintragsabfrage, gemessen {count['n']}"


def test_approval_reports_presence_warnings(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    e = _entry(_db_session, employee_user, time(8), time(12))
    cr = _cr(_db_session, employee_user, e, start=time(8), end=time(18))
    r = _review(admin_client, cr)
    assert r.status_code == 200, r.text
    assert {"WORK_WINDOW_CLAMPED", "PRESENCE_BREAK"} <= set(_codes(r))
