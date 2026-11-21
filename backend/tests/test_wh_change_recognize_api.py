"""Plan 2026-11-21 Task 4: Anerkennen beim Speichern einer Arbeitszeit-Änderung
(``recognize_entry_ids`` im Anlege- und Vorschau-Body).

Kundenfall vom 20.11.2026 über die API: erster Arbeitstag 01.10., Basiszeile mit
Blöcken an allen fünf Werktagen, die Änderung ab 01.10. setzt Blöcke nur an
Mo + Di. Die Aushilfe-Einträge an Mi 07.10. und Do 08.10. fielen damit auf 0 h
(Werktag ohne Block) — gewählt werden sie im selben Schritt anerkannt, und die
Änderung ist keine Verkürzung mehr (kein Schutzpaket)."""
import uuid
from datetime import date
from types import SimpleNamespace

import pytest

from app.models import TimeEntry, TimeEntryAuditLog
from app.services.credit_override_service import RECOGNIZE_LIMIT, RECOGNIZE_LIMIT_DETAIL
from app.services import calculation_service, credit_override_service as cos, reclamp_audit
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app
from tests.wh_change_helpers import (
    add_row, admin_client, changes_url, entry, freeze, reclamp_logs, rows_of, t,
)
from tests.work_blocks_fixtures import block_week

TODAY = date(2026, 11, 20)     # Freitag — Tag des Kundenfalls
FIRST = date(2026, 10, 1)      # erster Arbeitstag (Donnerstag)
WED, THU, MON, TUE = date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 12), date(2026, 10, 13)

_BASE_DAY = [("07:55", "13:25"), ("14:55", "17:55")]
BASE_WEEK = block_week(mon=_BASE_DAY, tue=_BASE_DAY, wed=_BASE_DAY, thu=_BASE_DAY, fri=_BASE_DAY)
# Mo + Di mit früherem Beginn: Hülle ab 07:15 statt 07:40 — der Montag gewinnt.
_NEW_DAY = [("07:30", "13:00"), ("14:30", "17:30")]
MON_TUE = block_week(mon=_NEW_DAY, tue=_NEW_DAY)


@pytest.fixture
def client(db, test_admin, monkeypatch):
    freeze(monkeypatch, TODAY)
    yield admin_client(db, test_admin)
    test_app.dependency_overrides.clear()


@pytest.fixture
def case(db, test_user):
    """Basiszeile ab 01.10. und drei geschlossene Einträge: Mi 07.10. 07:50–12:05,
    Do 08.10. 07:50–12:35 (beide ungekappt), Mo 12.10. 07:40–12:00 (Stempel ab
    07:35, von der Basis-Hülle gekappt — die Änderung gibt ihm 5 Minuten zurück)."""
    test_user.first_work_day = FIRST
    db.commit()
    add_row(db, test_user, FIRST, note=reclamp_audit.BASELINE_ROW_NOTE, week=BASE_WEEK)
    return SimpleNamespace(
        user=test_user,
        wed=entry(db, test_user, WED, t(7, 50), t(12, 5)),
        thu=entry(db, test_user, THU, t(7, 50), t(12, 35)),
        mon=entry(db, test_user, MON, t(7, 40), t(12), raw_start=t(7, 35)),
    )


def _body(*ids, **extra) -> dict:
    return {"effective_from": FIRST.isoformat(), "blocks": MON_TUE,
            "recognize_entry_ids": [str(i) for i in ids], **extra}


def _fresh(db, e) -> TimeEntry:
    db.expire_all()
    return db.get(TimeEntry, e.id)


def _override_rows(db, user) -> dict:
    return {r.time_entry_id: r for r in db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.user_id == user.id,
        TimeEntryAuditLog.tenant_id == DEFAULT_TENANT_ID,
        TimeEntryAuditLog.source == cos.CREDIT_OVERRIDE_SOURCE,
    ).all()}


def _overtime(db, user) -> float:
    db.expire_all()
    cutoff = calculation_service.get_soll_cutoff_date(db, user)
    return float(calculation_service.get_overtime_account(db, user, TODAY.year, TODAY.month, cutoff_date=cutoff))


def _assert_unchanged(db, case) -> None:
    """Nichts gespeichert: nur die Basiszeile, kein Eintrag anerkannt, kein Protokoll."""
    [row] = rows_of(db, case.user)
    assert (row.effective_from, row.note, row.blocks) == (FIRST, reclamp_audit.BASELINE_ROW_NOTE, BASE_WEEK)
    for e in (case.wed, case.thu, case.mon):
        assert _fresh(db, e).credit_override is False
    assert _override_rows(db, case.user) == {}
    assert reclamp_logs(db, case.user) == []


def test_create_with_selection_needs_no_reason(client, db, case):
    r = client.post(changes_url(case.user), json=_body(case.wed.id, case.thu.id))
    assert r.status_code == 201, r.text
    # Die anerkannten Einträge zählen nicht als „neu berechnet" (nur der 12.10.).
    assert r.json()["adjusted_time_entries"] == 1
    assert _fresh(db, case.wed).credit_override is True
    assert _fresh(db, case.thu).credit_override is True

    j = client.get(f"/api/admin/users/{case.user.id}/journal", params={"year": 2026, "month": 10})
    assert j.status_code == 200, j.text
    days = {d["date"]: d for d in j.json()["days"]}
    assert days[WED.isoformat()]["target_hours"] == 0
    assert days[WED.isoformat()]["actual_hours"] == pytest.approx(4.25, abs=0.005)
    assert days[THU.isoformat()]["actual_hours"] == pytest.approx(4.75, abs=0.005)


def test_without_selection_still_requires_reason(client, db, case):
    """Gegenprobe: ohne Auswahl bleibt es die rückwirkende Verkürzung von heute."""
    r = client.post(changes_url(case.user), json=_body())
    assert r.status_code == 400, r.text
    assert r.json()["detail"].startswith("Rückwirkende Verkürzung (2 Einträge verlieren angerechnete Zeit)")
    _assert_unchanged(db, case)


def test_unselected_entry_still_requires_reason(client, db, case):
    """Review Focus 1: angewählt, wieder abgewählt, gespeichert — der abgewählte
    Eintrag wird nicht anerkannt, für ihn gilt das Schutzpaket wie heute."""
    r = client.post(changes_url(case.user), json=_body(case.wed.id))
    assert r.status_code == 400, r.text
    assert r.json()["detail"].startswith("Rückwirkende Verkürzung (1 Eintrag verliert angerechnete Zeit)")
    _assert_unchanged(db, case)


def test_preview_equals_save(client, db, case):
    body = _body(case.wed.id, case.thu.id)
    plain = client.post(f"{changes_url(case.user)}/preview", json=_body())
    assert plain.status_code == 200, plain.text
    assert plain.json()["is_shortening"] is True

    p = client.post(f"{changes_url(case.user)}/preview", json=body)
    assert p.status_code == 200, p.text
    preview = p.json()
    assert preview["blocked_reason"] is None
    assert preview["is_shortening"] is False
    assert preview["affected_time_entries"] == 1
    assert preview["lost_credited_hours"] == 0
    flags = {c["date"]: (c["recognizable"], c["recognized"], c["blockless_workday"])
             for c in preview["time_entry_changes"]}
    assert flags == {WED.isoformat(): (True, True, True), THU.isoformat(): (True, True, True),
                     MON.isoformat(): (True, False, False)}
    # Die Vorschau schreibt nichts.
    _assert_unchanged(db, case)

    before = _overtime(db, case.user)
    assert preview["overtime_before"] == pytest.approx(before, abs=0.005)
    r = client.post(changes_url(case.user), json=body)
    assert r.status_code == 201, r.text
    after = _overtime(db, case.user)
    assert after - before == pytest.approx(preview["saldo_delta_hours"], abs=0.005)
    assert after == pytest.approx(preview["overtime_after"], abs=0.005)


def test_summary_row_excludes_recognized(client, db, case):
    r = client.post(changes_url(case.user), json=_body(case.wed.id, case.thu.id))
    assert r.status_code == 201, r.text
    db.expire_all()
    [summary] = reclamp_logs(db, case.user, summary=True)
    parsed = reclamp_audit.parse_summary_note(summary.new_note)
    assert parsed.count == 1
    assert parsed.delta_minutes == 5          # nur der Gewinn am 12.10.
    assert parsed.shortening is False
    assert [x.time_entry_id for x in reclamp_logs(db, case.user, summary=False)] == [case.mon.id]
    rows = _override_rows(db, case.user)
    assert set(rows) == {case.wed.id, case.thu.id}
    assert (rows[case.wed.id].old_start_time, rows[case.wed.id].old_end_time) == (t(7, 50), t(12, 5))
    assert (rows[case.thu.id].old_start_time, rows[case.thu.id].old_end_time) == (t(7, 50), t(12, 35))


def test_recognize_collision_rolls_back_change(client, db, case):
    """Review Focus 4: Anerkennen legte den Beginn auf einen belegten Beginn →
    409 mit ``start_taken_detail``, die ganze Arbeitszeit-Änderung rollt zurück.

    An einem Werktag ohne Block verschiebt die Kappung den Beginn nie (Kollaps am
    Beginn), dort kann Anerkennen nicht kollidieren. Der Fall entsteht am
    Dienstag 13.10.: Stempel ab 07:00, die neue Hülle beginnt 07:15 — Anerkennen
    setzte den Beginn auf 07:00, wo schon ein (anerkannter) Eintrag beginnt."""
    early = entry(db, case.user, TUE, t(7, 40), t(12), raw_start=t(7, 0))
    entry(db, case.user, TUE, t(7, 0), t(7, 10), credit_override=True)
    r = client.post(changes_url(case.user), json=_body(case.wed.id, case.thu.id, early.id))
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == cos.start_taken_detail(t(7, 0))
    db.expire_all()
    [row] = rows_of(db, case.user)
    assert (row.note, row.blocks) == (reclamp_audit.BASELINE_ROW_NOTE, BASE_WEEK)
    for e in (case.wed, case.thu, early):
        assert _fresh(db, e).credit_override is False
    assert _fresh(db, early).start_time == t(7, 40)
    assert reclamp_logs(db, case.user) == []


def test_preview_collision_is_blocked_reason(client, db, case):
    """Die Vorschau wirft nie mitten im Dialog: ein Fehler beim Anerkennen wird
    ``blocked_reason`` (derselbe Text wie beim Speichern), die Liste der
    Einträge kommt trotzdem — ohne Anerkennen gerechnet."""
    early = entry(db, case.user, TUE, t(7, 40), t(12), raw_start=t(7, 0))
    entry(db, case.user, TUE, t(7, 0), t(7, 10), credit_override=True)
    p = client.post(f"{changes_url(case.user)}/preview", json=_body(case.wed.id, early.id))
    assert p.status_code == 200, p.text
    body = p.json()
    assert body["blocked_reason"] == cos.start_taken_detail(t(7, 0))
    assert {c["date"] for c in body["time_entry_changes"]} == {WED.isoformat(), THU.isoformat(),
                                                             MON.isoformat(), TUE.isoformat()}
    assert not any(c["recognized"] for c in body["time_entry_changes"])
    assert _fresh(db, early).credit_override is False
    assert reclamp_logs(db, case.user) == []


def test_preview_stale_selection_is_blocked_reason(client, db, case):
    """Eine gewählte ID, die das neue Wirkungsdatum nicht mehr betrifft, sperrt
    das Speichern mit dem Text des Speicherpfads — der Dialog bekommt die neue
    Liste und kann sie abwählen."""
    body = {**_body(case.wed.id), "effective_from": "2026-10-08"}
    p = client.post(f"{changes_url(case.user)}/preview", json=body)
    assert p.status_code == 200, p.text
    assert p.json()["blocked_reason"] == "Der Eintrag vom 07.10.2026 ist von dieser Änderung nicht betroffen."
    assert WED.isoformat() not in {c["date"] for c in p.json()["time_entry_changes"]}
    s = client.post(changes_url(case.user), json=body)
    assert s.status_code == 400, s.text
    assert s.json()["detail"] == p.json()["blocked_reason"]


def test_foreign_recognize_id_404(client, db, case, test_admin):
    """Eintrag einer anderen Person derselben Praxis → 404, nichts gespeichert."""
    foreign = entry(db, test_admin, WED, t(8), t(12))
    r = client.post(changes_url(case.user), json=_body(case.wed.id, case.thu.id, foreign.id))
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Zeiteintrag nicht gefunden"
    _assert_unchanged(db, case)
    assert _fresh(db, foreign).credit_override is False


def test_recognize_limit(client, db, case):
    ids = [uuid.uuid4() for _ in range(RECOGNIZE_LIMIT + 1)]
    r = client.post(changes_url(case.user), json=_body(*ids))
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == RECOGNIZE_LIMIT_DETAIL
    p = client.post(f"{changes_url(case.user)}/preview", json=_body(*ids))
    assert p.status_code == 200, p.text
    assert p.json()["blocked_reason"] == RECOGNIZE_LIMIT_DETAIL
