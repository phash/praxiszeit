"""Smoke-Fund 1.22.0: Betriebsferien-Zeilen an einem verkürzten Tag überleben
eine Arbeitszeit-Änderung.

``company_closures._create_closure_absences`` bucht an einem verkürzten Tag
(24.12. ``max_hours``, eigener ``ReducedDay``) und an einem ``half_day``-Sondertag
``hours = special_days_service.special_day_target(d, Tagessoll, cfg)`` mit
``half_day=False``. ``calculation_service.retarget_absence_hours`` zog genau diese
Zeilen bisher auf das UNGEWICHTETE Tagessoll (Fund A, die Konvention der
Direktbuchungen) — Annas 24.12. ging 4,00 h → 8,00 h. Die Zeilen mit
``closure_id`` folgen jetzt der Buchungsregel der Schließung; Direktbuchungen
behalten das ungewichtete Tagessoll.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, ReducedDay, TimeEntryAuditLog
from app.models.system_setting import SystemSetting
from app.services import calculation_service as cs
from app.services import journal_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

D23 = date(2026, 12, 23)
D24 = date(2026, 12, 24)
ROSE = date(2027, 2, 8)   # Rosenmontag 2027 (Montag), eigener verkürzter Tag
EFF = date(2026, 12, 1)   # Zukunft (heute 2026-11): kein Rückwirkungs-Schutzpaket


def _client(db, admin):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: admin
    test_app.dependency_overrides[require_admin] = lambda: admin
    return TestClient(test_app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    test_app.dependency_overrides.clear()


def _set(db, key, value):
    db.add(SystemSetting(key=key, tenant_id=DEFAULT_TENANT_ID, value=value, description=key))
    db.commit()


@pytest.fixture(params=["max_hours", "half_day"])
def mode(request, db, default_tenant):
    if request.param == "max_hours":
        _set(db, "special_day_dec24_mode", "max_hours")
        _set(db, "special_day_dec24_max_hours", "4")
    else:
        _set(db, "special_day_dec24_mode", "half_day")
    return request.param


def _rows(db, user):
    db.expire_all()
    return {a.date: a for a in db.query(Absence).filter(Absence.user_id == user.id).all()}


def _closure(client, start="2026-12-21", end="2026-12-31"):
    r = client.post("/api/company-closures/", json={
        "name": "BF", "start_date": start, "end_date": end, "counts_as_vacation": True})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _wh_change(client, user, weekly, eff=EFF):
    r = client.post(f"/api/admin/users/{user.id}/working-hours-changes",
                    json={"effective_from": eff.isoformat(), "weekly_hours": weekly})
    assert r.status_code == 201, r.text
    return r.json()


def _figures(db, user):
    """Alle Zahlen, die an der Zeile hängen könnten."""
    db.expire_all()
    rows = _rows(db, user)
    j = journal_service.get_journal(db, user, 2026, 12)
    day = next(d for d in j["days"] if str(d["date"]) == D24.isoformat())
    return {
        "used_days": float(cs.get_vacation_account(db, user, 2026)["used_days"]),
        "absence_days": float(cs.absence_days(db, user, [rows[D24]])),
        "target": float(cs.get_monthly_target(db, user, 2026, 12)),
        "actual": float(cs.get_monthly_actual(db, user, 2026, 12)),
        "journal_day": (day["target_hours"], day["actual_hours"]),
    }


@pytest.mark.parametrize("weekly, expected", [
    (40.0, {"max_hours": 4.0, "half_day": 4.0}),   # Tagessoll unverändert 8 h
    (30.0, {"max_hours": 4.0, "half_day": 3.0}),   # Tagessoll 6 h: min(6, 4) bzw. 0,5 × 6
    (20.0, {"max_hours": 4.0, "half_day": 2.0}),   # Tagessoll 4 h
])
def test_closure_row_keeps_the_reduced_target_after_a_wh_change(
        db, mode, test_user, test_admin, weekly, expected):
    client = _client(db, test_admin)
    _closure(client)
    before = _rows(db, test_user)
    assert before[D24].hours == 4.0 and before[D24].half_day is False
    raw_before = before[D24].raw_hours
    figures_before = _figures(db, test_user)

    _wh_change(client, test_user, weekly)

    after = _rows(db, test_user)
    assert after[D24].hours == expected[mode], "Schließungszeile folgt special_day_target"
    assert after[D24].half_day is False
    assert after[D24].raw_hours == raw_before, "raw_hours bleibt unberührt"
    assert after[D23].hours == weekly / 5, "normaler Schließtag: volles neues Tagessoll"
    if weekly == 40.0:
        assert _figures(db, test_user) == figures_before


@pytest.mark.parametrize("split", [False, True])
def test_retarget_is_idempotent_and_resave_keeps_rows(db, mode, test_user, test_admin, split):
    """Mit #314-Schalter AN bucht ``update_closure`` per Delete + Re-Split neu —
    vorher stand danach wieder 4 h, nach der nächsten Änderung wieder 8 h."""
    if split:
        _set(db, "closure_overtime_after_vacation", "true")
    client = _client(db, test_admin)
    cid = _closure(client)
    _wh_change(client, test_user, 30.0)
    rows = {d: (a.type, a.hours) for d, a in _rows(db, test_user).items()}

    # Ein zweiter Lauf über dasselbe Fenster ändert nichts mehr.
    assert cs.retarget_absence_hours(
        db, test_user, date(2026, 12, 1), date(2026, 12, 31),
        old_full_target_by_date=cs.absence_full_targets(db, test_user, date(2026, 12, 1),
                                                        date(2026, 12, 31)),
        dry_run=True) == []

    # Neuspeichern der Schließung bucht dieselben Zeilen (keine Ping-Pong-Werte).
    r = client.put(f"/api/company-closures/{cid}", json={
        "name": "BF umbenannt", "start_date": "2026-12-21", "end_date": "2026-12-31",
        "counts_as_vacation": True})
    assert r.status_code == 200, r.text
    assert {d: (a.type, a.hours) for d, a in _rows(db, test_user).items()} == rows


def test_no_audit_row_for_the_untouched_closure_day(db, mode, test_user, test_admin):
    """Gleiches Tagessoll ⇒ die Rückrechnung fasst den 24.12. nicht an und
    protokolliert ihn auch nicht."""
    client = _client(db, test_admin)
    _closure(client)
    body = _wh_change(client, test_user, 40.0)
    assert body["adjusted_absences"] == 0
    assert db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.user_id == test_user.id,
        TimeEntryAuditLog.source == "wh_change",
        TimeEntryAuditLog.old_date == D24,
    ).count() == 0


def test_direct_vacation_on_reduced_day_keeps_unweighted_target(db, mode, test_user, test_admin):
    """Kontrolle: Direktbuchung (ohne ``closure_id``) trägt weiter das
    ungewichtete Tagessoll (Fund A)."""
    a = Absence(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=D24,
                type=AbsenceType.VACATION, hours=8.0, half_day=False)
    db.add(a)
    db.commit()
    _wh_change(_client(db, test_admin), test_user, 30.0)
    assert _rows(db, test_user)[D24].hours == 6.0


def test_reduced_day_row_closure(db, default_tenant, test_user, test_admin):
    """Eigener verkürzter Tag (``reduced_days``), nicht nur der 24.12."""
    db.add(ReducedDay(tenant_id=DEFAULT_TENANT_ID, date=ROSE, label="Rosenmontag",
                      max_hours=4))
    db.commit()
    client = _client(db, test_admin)
    _closure(client, "2027-02-08", "2027-02-09")
    assert _rows(db, test_user)[ROSE].hours == 4.0
    _wh_change(client, test_user, 30.0)
    rows = _rows(db, test_user)
    assert rows[ROSE].hours == 4.0
    assert rows[date(2027, 2, 9)].hours == 6.0


@pytest.mark.parametrize("mode, kept_until, expected", [
    ("max_hours", 11, 1.0),   # verkürzt auf 4 h, 3 h gearbeitet → Rest 1 h
    ("half_day", 9, 3.0),     # 0,5 × 8 = 4 h, 1 h gearbeitet → Rest 3 h
], indirect=["mode"])
def test_f1_clamp_on_closure_row_uses_the_weighted_target(
        db, mode, kept_until, expected, test_user, test_admin):
    """Review Fix-Runde 1: bleibt am Schließtag ein Zeiteintrag stehen, klemmt
    die Rückrechnung die Betriebsferien-Zeile auf den nicht gearbeiteten Rest des
    VERKÜRZTEN Tagessolls (Gutschrifts-Einheiten, Gewicht 1 — der Faktor steckt
    schon im Wert)."""
    from datetime import time
    from app.models import TimeEntry
    client = _client(db, test_admin)
    _closure(client)
    db.add(TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=D24,
                     start_time=time(8, 0), end_time=time(kept_until, 0), break_minutes=0))
    db.commit()
    _wh_change(client, test_user, 40.0)
    assert _rows(db, test_user)[D24].hours == expected


def test_stale_closure_row_on_a_day_that_became_free_goes_to_zero(db, default_tenant, test_user, test_admin):
    """Review Fix-Runde 1 (Minor 3): ist der 24.12. inzwischen ``free`` (ohne
    Neubuchung der Schließung), zieht die Rückrechnung die Zeile wie die
    Buchungsregel auf ``special_day_target`` = 0."""
    _set(db, "special_day_dec24_mode", "max_hours")
    _set(db, "special_day_dec24_max_hours", "4")
    client = _client(db, test_admin)
    _closure(client)
    assert _rows(db, test_user)[D24].hours == 4.0
    row = db.query(SystemSetting).filter(SystemSetting.key == "special_day_dec24_mode").one()
    row.value = "free"
    db.commit()
    _wh_change(client, test_user, 40.0)
    rows = _rows(db, test_user)
    assert rows[D24].hours == 0.0
    assert rows[D23].hours == 8.0
