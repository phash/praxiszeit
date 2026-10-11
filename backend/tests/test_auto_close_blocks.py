"""Spec K15, P18, E42: der Auto-Close kappt jetzt und kennzeichnet sich."""
import datetime as dt
from datetime import date, time
from decimal import Decimal

import pytest

from app.models import ChangeRequest, PublicHoliday, TimeEntry, TimeEntryAuditLog
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.models.system_setting import SystemSetting
from app.services import work_window_service
from app.services.holiday_service import invalidate_holiday_cache
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, admin_client, admin_user, employee_client, employee_user, tenant,
)
from tests.work_blocks_fixtures import K_BLOCKS, MON, block_week, legacy_week

import app.routers.time_entries as te

TUE = date(2026, 6, 2)


def _open(db, user, start=time(8, 0), **kw):
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=user.id, date=MON,
                  start_time=start, end_time=None, break_minutes=0, **kw)
    db.add(e)
    db.commit()
    return e


def _next_day_clock_in(client, monkeypatch):
    monkeypatch.setattr(te, "_today_local", lambda: TUE)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 2, 7, 30))
    resp = client.post("/api/time-entries/clock-in", json={})
    assert resp.status_code == 201, resp.text


def test_k15_auto_close_clamps_and_flags(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _next_day_clock_in(employee_client, monkeypatch)
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.uncredited_minutes) == (time(18, 15), time(23, 59), 150)
    assert (e.auto_closed, e.clamp_grace_minutes, e.net_hours) == (True, 15, Decimal("7.75"))
    audit = _db_session.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.time_entry_id == e.id, TimeEntryAuditLog.source == "auto_close").one()
    assert audit.new_end_time == time(18, 15)


def test_without_blocks_end_stays_2359(_db_session, employee_user, employee_client, monkeypatch):
    e = _open(_db_session, employee_user)
    _next_day_clock_in(employee_client, monkeypatch)
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(23, 59), None, True)


def test_auto_close_uses_stored_grace(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    _db_session.add(SystemSetting(key="work_window_grace_minutes", value="0", tenant_id=DEFAULT_TENANT_ID))
    _db_session.commit()
    e = _open(_db_session, employee_user, clamp_grace_minutes=15)
    _next_day_clock_in(employee_client, monkeypatch)
    _db_session.refresh(e)
    # Spec 17 (test_clamp_grace, E80): weiter mit 15 gekappt UND der Puffer
    # bleibt 15 gespeichert — sonst kappte jede spätere Einzel-Neukappung
    # (Admin-Bearbeitung, Datumswechsel, CR-UPDATE) mit dem gesenkten Wert 0.
    assert (e.end_time, e.raw_end_time, e.clamp_grace_minutes, e.auto_closed) == (
        time(18, 15), time(23, 59), 15, True)
    assert e.net_hours == Decimal("7.75")  # angerechnete Zeit unverändert


def test_clock_status_stale_branch_closes_with_clamp(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    monkeypatch.setattr(te, "_today_local", lambda: TUE)
    assert employee_client.get("/api/time-entries/clock-status").json()["is_clocked_in"] is False
    _db_session.refresh(e)
    assert (e.end_time, e.auto_closed) == (time(18, 15), True)


def _auto_close_directly(db, entry):
    """Ein Test mit ``admin_client`` UND ``employee_client`` sähe beide als
    dieselbe Person — beide Fixtures überschreiben ``get_current_user``, die
    zuletzt gebaute gewinnt. Deshalb den Auto-Close hier direkt aufrufen."""
    te._close_stale_entry(db, entry)
    db.commit()


def test_admin_end_correction_resets_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    assert e.auto_closed is True
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={"end_time": "17:00"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(17, 0), None, False)


def test_admin_form_resave_keeps_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    resp = admin_client.put(f"/api/admin/time-entries/{e.id}", json={
        "start_time": "08:00", "end_time": "18:15", "note": "geprüft"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(18, 15), time(23, 59), True)


# Review Focus 1: halboffenes Altfenster (Platzhalter 23:59) — wie 072.
def test_half_open_legacy_window_unchanged(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = legacy_week(mon=("08:00", None))
    _db_session.commit()
    e = _open(_db_session, employee_user, start=time(9, 0))
    _next_day_clock_in(employee_client, monkeypatch)
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.uncredited_minutes, e.auto_closed) == (time(23, 59), None, 0, True)


def test_half_open_legacy_window_late_clock_out(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = legacy_week(mon=("08:00", None))
    _db_session.commit()
    e = _open(_db_session, employee_user, start=time(9, 0))
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 22, 30))
    assert employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 45}).status_code == 200
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(22, 30), None, False)


# P18 (7.1): „Jeder Pfad außer dem Auto-Close, der end_time schreibt, setzt
# auto_closed = false" — auch Ausstempeln, die Bearbeiten-Route der Beschäftigten
# (Admins bearbeiten dort auch fremde Einträge vergangener Tage) und die
# Genehmigung eines Änderungsantrags (UPDATE). Ein unverändert mitgeschicktes
# wirksames Ende ist keine Korrektur: dann bleibt 23:59 synthetisch.

def test_clock_out_resets_flag(_db_session, employee_user, employee_client, monkeypatch):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    # Künstlicher Zustand (offener Eintrag mit Kennzeichen): hält fest, dass
    # clock_out das Kennzeichen selbst schreibt, statt sich auf den Default zu verlassen.
    e = _open(_db_session, employee_user, auto_closed=True)
    monkeypatch.setattr(te, "_today_local", lambda: MON)
    monkeypatch.setattr(te, "_now_local", lambda: dt.datetime(2026, 6, 1, 17, 0))
    resp = employee_client.post("/api/time-entries/clock-out", json={"break_minutes": 30})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.auto_closed) == (time(17, 0), False)


def test_employee_route_end_correction_resets_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    resp = admin_client.put(f"/api/time-entries/{e.id}", json={"end_time": "17:00"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(17, 0), None, False)


def test_employee_route_form_resave_keeps_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    resp = admin_client.put(f"/api/time-entries/{e.id}", json={
        "start_time": "08:00", "end_time": "18:15", "note": "geprüft"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(18, 15), time(23, 59), True)


def _approve_update_cr(db, client, user, entry, end, start=time(8, 0)):
    cr = ChangeRequest(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.UPDATE, status=ChangeRequestStatus.PENDING,
                       time_entry_id=entry.id, proposed_date=MON, proposed_start_time=start,
                       proposed_end_time=end, proposed_break_minutes=0,
                       reason="Ende nachgetragen")
    db.add(cr)
    db.commit()
    resp = client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    return resp


def test_cr_update_end_correction_resets_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    _approve_update_cr(_db_session, admin_client, employee_user, e, time(17, 0))
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(17, 0), None, False)


def test_cr_update_unchanged_end_keeps_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    _approve_update_cr(_db_session, admin_client, employee_user, e, time(18, 15))
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(18, 15), time(23, 59), True)


# Review Task 8 (P18): die Waiver-Rückfrage der MA-Route füllt ein fehlendes Ende
# selbst auf — dort entstand der Antrag ganz ohne Eingabe. Beim automatisch
# geschlossenen Eintrag nimmt sie das WIRKSAME Ende, nie das Rohende 23:59: der
# Antrag behauptet kein Ende, das niemand eingetragen hat, und die Genehmigung
# erkennt darin das unveränderte Ende (Kennzeichen bleibt). Seit der Entscheidung
# vom 2026-10-11 (unten) ist das die Voraussetzung dafür, dass ein 23:59 nur noch
# aus echter Eingabe kommen kann.

def test_waiver_cr_without_end_keeps_flag(_db_session, employee_user, admin_client):
    employee_user.work_blocks = legacy_week(mon=("08:00", "17:00"))
    _db_session.add(SystemSetting(key="break_exception_requires_approval", value="true",
                                  tenant_id=DEFAULT_TENANT_ID))
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(17, 15), time(23, 59), True)
    # Nur Notiz + Ausnahmegrund; §4 (9:15 h ohne Pause) verlangt die Ausnahme,
    # der Mandant die Genehmigung → 202 + Antrag.
    resp = admin_client.put(f"/api/time-entries/{e.id}", json={
        "note": "nachgetragen", "break_waiver_reason": "Notfall"})
    assert resp.status_code == 202, resp.text
    cr = _db_session.query(ChangeRequest).filter(ChangeRequest.time_entry_id == e.id).one()
    # Der Antrag behauptet kein Ende 23:59, das niemand eingetragen hat.
    assert cr.proposed_end_time == time(17, 15)
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(17, 15), time(23, 59), True)


@pytest.mark.parametrize("route", ["/api/admin/time-entries", "/api/time-entries"],
                         ids=["admin-route", "ma-route"])
def test_partial_put_without_end_keeps_flag(_db_session, employee_user, admin_client, route):
    """Ein PUT ohne Ende (nur Pause/Notiz) ist keine Korrektur. Die Verwaltungsroute
    setzte für das fehlende Ende bis 2026-10-11 das ROHENDE ein — seit 23:59 als
    Korrektur gilt, nimmt sie das wirksame Ende (``end_input_for`` stellt daraus
    am selben Tag das Protokoll-23:59 wieder her)."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    resp = admin_client.put(f"{route}/{e.id}", json={"note": "geprüft"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed, e.note) == (
        time(18, 15), time(23, 59), True, "geprüft")


# Entschieden 2026-10-11 (Produktinhaber, P18): ein echtes Ende 23:59 ist
# eintragbar. Die Formulare zeigen und schicken bei ``auto_closed`` das wirksame
# Ende (18:15), und kein Pfad füllt ein fehlendes Ende mit dem Rohende auf — ein
# 23:59 kommt also nur aus echter Eingabe und ist eine Korrektur: das Kennzeichen
# fällt, 23:59 steht als echter Stempel in ``raw_end_time`` und wird gegen die
# Hülle gekappt wie jedes andere Ende. Bis dahin hielten alle drei Schreibpfade
# ein eingereichtes 23:59 pauschal für das Echo des synthetischen Rohendes
# (Review Task 8); die Tests ``test_*_raw_end_keeps_flag`` hielten diese alte
# Regel fest und sind deshalb umgedreht. Mit Sekunden („23:59:30") ist es
# dieselbe echte Eingabe.

def _assert_typed_2359(e, end):
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(18, 15), end, False)
    assert (e.uncredited_minutes, e.net_hours) == (150, Decimal("7.75"))
    # P19: die Hüllenminuten am Ende (18:15–23:59) zählen jetzt als „nicht
    # angerechnet" — 23:59 ist ein Stempel.
    assert work_window_service.not_credited_minutes(e) == 150 + 344


def _has_end_clamp_warning(resp):
    return any(w.startswith("WORK_WINDOW_CLAMPED") and "Ende 23:59 → 18:15" in w
               for w in resp.json()["warnings"])


@pytest.mark.parametrize("end", [time(23, 59), time(23, 59, 30)])
def test_cr_update_typed_2359_is_a_correction(_db_session, employee_user, admin_client, end):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    resp = _approve_update_cr(_db_session, admin_client, employee_user, e, end)
    _db_session.refresh(e)
    _assert_typed_2359(e, end)
    assert _has_end_clamp_warning(resp)


@pytest.mark.parametrize("route", ["/api/admin/time-entries", "/api/time-entries"],
                         ids=["admin-route", "ma-route"])
@pytest.mark.parametrize("end", ["23:59", "23:59:30"])
def test_route_typed_2359_is_a_correction(_db_session, employee_user, admin_client, route, end):
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    resp = admin_client.put(f"{route}/{e.id}", json={"end_time": end})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    _assert_typed_2359(e, time.fromisoformat(end))
    # Gekappt wie jedes andere Ende — und gemeldet (#462): die Rohzeiten sind
    # dieselben wie vorher, aber 23:59 ist jetzt ein Stempel, keine Protokollzeile.
    assert _has_end_clamp_warning(resp)


def _as_admin(admin_user):
    """Nach einem Schritt als Beschäftigte die Verwaltung handeln lassen —
    dieselben Überschreibungen wie ``admin_client``, im selben Client."""
    from tests.test_endpoints import endpoints_app, get_current_user, require_admin
    endpoints_app.dependency_overrides[get_current_user] = lambda: admin_user
    endpoints_app.dependency_overrides[require_admin] = lambda: admin_user


def _employee_request(client, entry, end):
    return client.post("/api/change-requests/", json={
        "request_type": "update", "time_entry_id": str(entry.id),
        "proposed_date": MON.isoformat(), "proposed_start_time": "08:00",
        "proposed_end_time": end, "proposed_break_minutes": 0,
        "reason": "Ende nachgetragen"})


def test_employee_request_typed_2359_is_a_correction(_db_session, employee_user, admin_user,
                                                    employee_client):
    """MA-Antrag samt Genehmigung: das eingetragene 23:59 wird angenommen und
    gespeichert (roh, E40), die Genehmigung hebt das Kennzeichen auf."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    resp = _employee_request(employee_client, e, "23:59")
    assert resp.status_code == 201, resp.text
    cr = _db_session.query(ChangeRequest).one()
    assert cr.proposed_end_time == time(23, 59)
    _as_admin(admin_user)
    resp = employee_client.post(f"/api/admin/change-requests/{cr.id}/review",
                                json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    _assert_typed_2359(e, time(23, 59))


def test_employee_request_effective_end_keeps_flag(_db_session, employee_user, admin_user,
                                                   employee_client):
    """Gegenprobe: der Antrag schickt das vorbelegte wirksame Ende 18:15 zurück
    (nur Begründung/Pause geändert) — keine Korrektur, das Kennzeichen bleibt."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = _open(_db_session, employee_user)
    _auto_close_directly(_db_session, e)
    resp = _employee_request(employee_client, e, "18:15")
    assert resp.status_code == 201, resp.text
    cr = _db_session.query(ChangeRequest).one()
    _as_admin(admin_user)
    resp = employee_client.post(f"/api/admin/change-requests/{cr.id}/review",
                                json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(18, 15), time(23, 59), True)


def test_cr_create_with_2359_is_a_stamp(_db_session, employee_user, admin_client):
    """CREATE-Genehmigung: ein neuer Eintrag 08:00–23:59 trägt nie ein
    Kennzeichen — 23:59 ist der Stempel, gekappt auf die Hülle."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    cr = ChangeRequest(user_id=employee_user.id, tenant_id=DEFAULT_TENANT_ID, entry_kind="time_entry",
                       request_type=ChangeRequestType.CREATE, status=ChangeRequestStatus.PENDING,
                       proposed_date=MON, proposed_start_time=time(8, 0),
                       proposed_end_time=time(23, 59), proposed_break_minutes=0,
                       reason="Stempeln vergessen")
    _db_session.add(cr)
    _db_session.commit()
    resp = admin_client.post(f"/api/admin/change-requests/{cr.id}/review", json={"action": "approve"})
    assert resp.status_code == 200, resp.text
    e = _db_session.query(TimeEntry).one()
    _assert_typed_2359(e, time(23, 59))


def test_without_blocks_typed_2359_stays_echo(_db_session, employee_user, admin_client):
    """Grenzfall (Entschieden 2026-10-11): ohne Blöcke wird nicht gekappt, das
    wirksame Ende ist selbst 23:59 — ein zurückgeschicktes 23:59 ist vom Echo des
    Formulars nicht zu unterscheiden und bleibt Echo (Kennzeichen bleibt), an
    allen drei Schreibpfaden. Beginn 18:00, damit §3/§4 nicht anschlagen."""
    e = _open(_db_session, employee_user, start=time(18, 0))
    _auto_close_directly(_db_session, e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(23, 59), None, True)
    for route in ("/api/admin/time-entries", "/api/time-entries"):
        resp = admin_client.put(f"{route}/{e.id}", json={"end_time": "23:59"})
        assert resp.status_code == 200, resp.text
        _db_session.refresh(e)
        assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(23, 59), None, True)
    _approve_update_cr(_db_session, admin_client, employee_user, e, time(23, 59), start=time(18, 0))
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(23, 59), None, True)


# Je Fall: Aufbau, Rückgabe = erwarteter gespeicherter Puffer nach dem Auto-Close.
# 15 belegt, dass gegen die Blöcke gekappt wurde (nur eben nicht unter 23:59) —
# sonst bestünde der Test auch, wenn die Blöcke gar nicht griffen.
def _ungekappt_track_hours_off(db, user):
    user.work_blocks = K_BLOCKS
    user.track_hours = False
    return None


def _ungekappt_feiertag(db, user):
    user.work_blocks = K_BLOCKS
    db.add(PublicHoliday(date=MON, name="Testfeiertag", year=MON.year, tenant_id=DEFAULT_TENANT_ID))
    invalidate_holiday_cache()  # F-034: Feiertage sind prozessweit gecacht
    return None


def _ungekappt_halboffen(db, user):
    user.work_blocks = legacy_week(mon=("08:00", None))
    return 15


def _ungekappt_huelle_bis_2359(db, user):
    # 23:50 + Puffer 15 → Hülle auf 23:59 begrenzt (``_shift_min``).
    user.work_blocks = block_week(mon=[("16:00", "23:50")])
    return 15


@pytest.fixture
def _fresh_holiday_cache():
    """Der Feiertag dieses Tests darf nicht im Prozess-Cache (F-034) hängen
    bleiben — die DB ist je Test frisch, der Cache nicht."""
    invalidate_holiday_cache()
    yield
    invalidate_holiday_cache()


@pytest.mark.parametrize("setup", [
    _ungekappt_track_hours_off, _ungekappt_feiertag, _ungekappt_halboffen, _ungekappt_huelle_bis_2359,
], ids=["track_hours_off", "feiertag", "halboffenes_altfenster", "huelle_bis_2359"])
def test_unclamped_end_2359_stays_echo_beyond_no_blocks(_db_session, employee_user, admin_client, setup,
                                                         _fresh_holiday_cache):
    """Review V1 (Grenzfall P18): der Grenzfall hängt nicht an „ohne Blöcke", sondern daran,
    dass der Auto-Close das 23:59 NICHT kappt — das wirksame Ende ist dann selbst
    23:59, ein eingetragenes 23:59 bleibt Echo. Auch MIT hinterlegten Blöcken:
    ohne Stundenzählung (#191), am Feiertag (#484), bei halboffenem Altfenster
    (Spec 5.3) und wenn die Hülle über den Puffer bis 23:59 reicht. Belegt den
    Spec-Wortlaut (P18, 7.1, Pflichtinhalt 9) — keine Codeänderung."""
    grace = setup(_db_session, employee_user)
    _db_session.commit()
    e = _open(_db_session, employee_user, start=time(18, 0))
    _auto_close_directly(_db_session, e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(23, 59), None, True)
    assert e.clamp_grace_minutes == grace
    for route in ("/api/admin/time-entries", "/api/time-entries"):
        resp = admin_client.put(f"{route}/{e.id}", json={"end_time": "23:59"})
        assert resp.status_code == 200, resp.text
        _db_session.refresh(e)
        assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(23, 59), None, True)
    _approve_update_cr(_db_session, admin_client, employee_user, e, time(23, 59), start=time(18, 0))
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(23, 59), None, True)


def test_raw_end_of_regular_entry_is_still_a_correction(_db_session, employee_user, admin_client):
    """Gegenprobe: ohne ``auto_closed`` ist der Rohwert ein echter Stempel — ihn
    erneut einzutragen bleibt eine gewöhnliche Eingabe (kein Kennzeichen)."""
    employee_user.work_blocks = K_BLOCKS
    _db_session.commit()
    e = TimeEntry(tenant_id=DEFAULT_TENANT_ID, user_id=employee_user.id, date=MON,
                  start_time=time(8, 0), end_time=time(18, 15), raw_end_time=time(19, 0),
                  break_minutes=0, uncredited_minutes=150)
    _db_session.add(e)
    _db_session.commit()
    _approve_update_cr(_db_session, admin_client, employee_user, e, time(19, 0))
    _db_session.refresh(e)
    assert (e.end_time, e.raw_end_time, e.auto_closed) == (time(18, 15), time(19, 0), False)


# Entschieden 2026-10-11: Korrektur ist jedes Ende außer dem gespeicherten
# wirksamen (minutengenau, Review Task 6). Rohende und Kennzeichen spielen keine
# Rolle mehr — die Formulare schicken das wirksame Ende, ein anderes Ende kommt
# nur aus echter Eingabe.
@pytest.mark.parametrize("incoming, eff, expected", [
    (time(18, 15), time(18, 15), False),       # Formular schickt wirksames Ende
    (time(18, 15, 30), time(18, 15), False),   # minutengenau: Sekunden machen keine Korrektur
    (time(17, 0), time(18, 15), True),         # echtes Ende eingetragen
    (time(17, 0, 30), time(18, 15), True),
    (time(23, 59), time(18, 15), True),        # 23:59 eingetragen (bis 2026-10-11: Echo)
    (time(23, 59, 30), time(18, 15), True),
    (time(18, 15), time(16, 15), True),        # nach Verschieben: Rohende 18:15 eingetragen
    (time(23, 59), time(23, 59), False),       # ungekappt (z. B. ohne Blöcke): 23:59 = wirksam (Grenzfall)
    (time(23, 59, 30), time(23, 59), False),
    (None, time(23, 59), True),                # Ende entfernt: Aufrufer entscheidet
])
def test_end_is_correction(incoming, eff, expected):
    from app.services.work_window_service import end_is_correction
    assert end_is_correction(incoming, eff) is expected
