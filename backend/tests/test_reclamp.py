"""Spec 9.3–9.5, 10, 11.2/11.4: Anlegen einer Arbeitszeit-Änderung (HTTP).

„heute" = Do 08.10.2026 10:00. Die Rechenregeln selbst prüft
test_wh_change_service.py; hier geht es um Sperre, Schutzpaket, 400/404/422,
Rollback, Antwortfelder und Protokoll."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

import app.routers.admin_users as admin_users_router
from app.core.audit_integrity import verify_row
from app.models import (
    AbsenceType, TimeEntry, TimeEntryAuditLog, User, UserRole, WorkingHoursChange, YearCarryover,
)
from app.services import calculation_service, lifecycle_service, reclamp_audit, wh_change_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app
from tests.wh_change_helpers import (
    ANNA_WEEK, EFF, MONDAYS, RETRO_REASON, absence, add_row, admin_client, entry, freeze, reclamp_logs,
    set_grace, t, with_pauses,
)
from tests.work_blocks_fixtures import K_BLOCKS, block_week, legacy_week

TUE_THU = dict(tue=[("08:00", "12:00")], thu=[("08:00", "12:00")])
SHORT = block_week(mon=[("08:00", "12:00"), ("15:00", "17:00")], **TUE_THU)
LONGER = block_week(mon=[("08:00", "12:00"), ("15:00", "19:00")], **TUE_THU)
REASON_TEXT = RETRO_REASON["retroactive_reason_text"]


@pytest.fixture
def client(db, test_admin, monkeypatch):
    freeze(monkeypatch)
    c = admin_client(db, test_admin)
    yield c
    test_app.dependency_overrides.clear()


def _post(client, user, body):
    return client.post(f"/api/admin/users/{user.id}/working-hours-changes", json=body)


def _anna(db, user):
    add_row(db, user, date(2026, 3, 1), week=ANNA_WEEK)
    absence(db, user, MONDAYS[0], AbsenceType.VACATION, 7.0)
    for d in MONDAYS[1:]:
        entry(db, user, d, t(8), t(12))
        entry(db, user, d, t(15), t(18), credit_override=(d == MONDAYS[3]))


def _employee(db, username, **kw):
    u = User(username=username, email=f"{username}@x.de", password_hash="h", first_name=username, last_name="T",
             role=UserRole.EMPLOYEE, weekly_hours=40.0, work_days_per_week=5, vacation_days=30,
             tenant_id=DEFAULT_TENANT_ID, **kw)
    db.add(u)
    db.commit()
    return u


class TestShorteningByEntries:
    def test_without_reason_is_400_and_changes_nothing(self, client, db, test_user):
        _anna(db, test_user)
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT})
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"] == (
            "Rückwirkende Verkürzung (3 Einträge verlieren angerechnete Zeit): Bitte Grund, Begründung und die "
            "Bestätigung zum Vergütungsrisiko angeben – oder die Änderung ab dem 08.10.2026 wirksam werden lassen.")
        db.expire_all()
        assert db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == test_user.id).count() == 1
        afternoons = db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id, TimeEntry.start_time == t(15)).all()
        assert {e.end_time for e in afternoons} == {t(18)}
        assert reclamp_logs(db, test_user) == []

    def test_stale_entry_closing_is_rolled_back_with_the_400(self, client, db, test_user):
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        stale = entry(db, test_user, date(2026, 10, 6), t(8), None)
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "11:00")],
                          thu=[("08:00", "12:00")])
        assert _post(client, test_user, {"effective_from": "2026-09-01", "blocks": week}).status_code == 400
        db.expire_all()
        assert db.get(TimeEntry, stale.id).end_time is None

    def test_with_reason_saves_note_counts_and_audit(self, client, db, test_user, test_admin):
        _anna(db, test_user)
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT, **RETRO_REASON})
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["note"] == f"[Erfassungsfehler korrigiert] {REASON_TEXT}"
        assert (body["adjusted_time_entries"], body["skipped_time_entries"], body["adjusted_absences"]) == (3, 1, 1)
        assert body["blocks"] == SHORT
        rows = reclamp_logs(db, test_user, summary=False)
        assert len(rows) == 3
        first = next(r for r in rows if r.new_date == MONDAYS[1])
        assert (first.old_start_time, first.old_end_time, first.new_end_time, first.changed_by) == (
            t(15), t(18), t(17, 15), test_admin.id)
        assert first.old_note == "angerechnet 3:00 h"
        assert first.new_note == (
            "angerechnet 2:15 h, nicht angerechnet 0:45 h — Arbeitszeit-Änderung ab 01.09.2026 "
            f"· Grund: [Erfassungsfehler korrigiert] {REASON_TEXT}")
        [summary] = reclamp_logs(db, test_user, summary=True)
        assert (summary.changed_by, summary.new_date, summary.time_entry_id) == (test_admin.id, None, None)
        assert summary.new_note == (
            "Arbeitszeit-Änderung ab 01.09.2026: 3 Einträge neu berechnet, Δ -135 Min, Saldo Δ +105 Min, "
            f"1 übersprungen (1 anerkannt) · Puffer 15 Min · Verkürzung · Grund: [Erfassungsfehler korrigiert] "
            f"{REASON_TEXT} · Vertrag: Mo 08:00–12:00+15:00–18:00 / Di 08:00–12:00 / Do 08:00–12:00 → "
            "Mo 08:00–12:00+15:00–17:00 / Di 08:00–12:00 / Do 08:00–12:00")
        all_rows = reclamp_logs(db, test_user)
        assert all(verify_row(r) for r in all_rows) and all(len(r.source) <= 40 for r in all_rows)

    def test_sonstiges_needs_the_second_hook(self, client, db, test_user):
        _anna(db, test_user)
        body = {"effective_from": "2026-09-01", "blocks": SHORT, **RETRO_REASON,
                "retroactive_reason_type": "sonstiges"}
        resp = _post(client, test_user, body)
        assert (resp.status_code, resp.json()["detail"]) == (400, wh_change_service.SONSTIGES_CONFIRM_DETAIL)
        resp = _post(client, test_user, {**body, "other_reason_risk_confirmed": True})
        assert resp.status_code == 201, resp.text
        assert resp.json()["note"].startswith("[Sonstiges] ")

    def test_reason_text_with_nine_characters_is_422(self, client, db, test_user):
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 45,
                                         **RETRO_REASON, "retroactive_reason_text": "123456789"})
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"] == "Die Begründung muss mindestens 10 Zeichen lang sein."


class TestShorteningBySaldo:
    def test_target_raise_with_blocks_needs_a_reason(self, client, db, test_user):
        _anna(db, test_user)
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "blocks": LONGER})
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"].startswith("Rückwirkende Verkürzung (Überstundenkonto −")
        assert _post(client, test_user, {"effective_from": "2026-09-01", "blocks": LONGER,
                                         **RETRO_REASON}).status_code == 201

    def test_the_same_raise_from_today_needs_no_reason(self, client, db, test_user):
        _anna(db, test_user)
        assert _post(client, test_user, {"effective_from": "2026-10-08", "blocks": LONGER}).status_code == 201

    def test_pure_weekly_hours_raise_without_blocks(self, client, db, test_user):
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 45})
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"].startswith("Rückwirkende Verkürzung (Überstundenkonto −")

    def test_legacy_window_to_blocks_with_a_higher_target(self, client, db, test_user):
        window = ("08:00", "16:00")
        add_row(db, test_user, date(2026, 1, 1), weekly_hours=30,
                blocks=legacy_week(mon=window, tue=window, wed=window, thu=window, fri=window))
        day = [window]
        blocks = block_week(pause=30, mon=day, tue=day, wed=day, thu=day, fri=day)
        assert _post(client, test_user, {"effective_from": "2026-09-01", "blocks": blocks}).status_code == 400
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "blocks": blocks, **RETRO_REASON})
        assert resp.status_code == 201, resp.text
        assert resp.json()["adjusted_time_entries"] == 0

    def test_smaller_pause_raises_the_target(self, client, db, test_user):
        week = with_pauses(block_week(mon=[("08:00", "12:00"), ("15:00", "19:00")], **TUE_THU), mon=60)
        add_row(db, test_user, date(2026, 3, 1), week=week)
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "blocks": with_pauses(week, mon=30)})
        assert resp.status_code == 400, resp.text


class TestClosedYears:
    def _closed_2025(self, db, user):
        user.first_work_day = date(2025, 1, 1)
        db.add(YearCarryover(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, year=2026,
                             overtime_hours=Decimal("0"), vacation_days=Decimal("0"), source="year_closing"))
        db.commit()

    def test_shortening_into_a_closed_year_is_400_even_with_reason(self, client, db, test_user):
        self._closed_2025(db, test_user)
        resp = _post(client, test_user, {"effective_from": "2025-06-02", "weekly_hours": 45, **RETRO_REASON})
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"] == wh_change_service.closed_year_detail([2025])

    def test_lengthening_into_a_closed_year_only_warns(self, client, db, test_user):
        self._closed_2025(db, test_user)
        resp = _post(client, test_user, {"effective_from": "2025-06-02", "weekly_hours": 35})
        assert resp.status_code == 201, resp.text
        assert "Jahresabschluss 2025" in resp.json()["warning"]


class TestModesAndFlags:
    def test_blocks_with_weekly_hours_is_422(self, client, test_user):
        resp = _post(client, test_user, {"effective_from": "2026-11-02", "blocks": K_BLOCKS, "weekly_hours": 7})
        assert (resp.status_code, resp.json()["detail"]) == (422, "Tagesstunden werden aus den Arbeitszeit-Blöcken abgeleitet.")

    def test_track_hours_off_accepts_blocks_and_skips_entries(self, client, db):
        lead = _employee(db, "leitend3", track_hours=False)
        entry(db, lead, MONDAYS[1], t(8), t(18))
        resp = _post(client, lead, {"effective_from": "2026-09-01", "blocks": K_BLOCKS})
        assert resp.status_code == 201, resp.text
        assert (resp.json()["blocks"], resp.json()["hours_monday"]) == (K_BLOCKS, 7.0)
        assert (resp.json()["adjusted_time_entries"], resp.json()["skipped_time_entries"]) == (0, 1)

    @pytest.mark.parametrize("track_hours", [True, False])
    def test_switch_from_blocks_to_weekly_ends_the_blocks(self, client, db, track_hours):
        """P24 (19.1 Nr. 6): blocks = NULL ab dem Wirkungsdatum, auch bei
        track_hours=false; die Vorgängerzeile behält ihre Blöcke."""
        u = _employee(db, f"p24_{track_hours}", track_hours=track_hours)
        add_row(db, u, date(2026, 3, 1), week=ANNA_WEEK)
        resp = _post(client, u, {"effective_from": "2026-10-12", "weekly_hours": 15})
        assert resp.status_code == 201, resp.text
        assert resp.json()["blocks"] is None
        rows = db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == u.id).order_by(
            WorkingHoursChange.effective_from).all()
        assert [r.blocks for r in rows] == [ANNA_WEEK, None]

    def test_remove_legacy_window(self, client, db, test_user):
        legacy = legacy_week(mon=("08:00", "17:00"))
        add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, blocks=legacy)
        carried = _post(client, test_user, {"effective_from": "2026-10-12", "weekly_hours": 38})
        assert carried.json()["blocks"] == legacy
        removed = _post(client, test_user, {"effective_from": "2026-10-19", "weekly_hours": 38,
                                            "remove_legacy_window": True})
        assert removed.status_code == 201, removed.text
        assert removed.json()["blocks"] is None

    def test_reset_of_a_foreign_change_is_404(self, client, db, test_user):
        other = _employee(db, "fremd")
        foreign = add_row(db, other, date(2026, 3, 1), weekly_hours=30)
        resp = _post(client, test_user, {"effective_from": "2026-10-12", "weekly_hours": 30,
                                         "reset_of_change_id": str(foreign.id)})
        assert resp.status_code == 404, resp.text

    def test_saturday_effective_date(self, client, db, test_user):
        """Review Focus 3: Wirkungsdatum Samstag 01.08.2026."""
        _anna(db, test_user)
        resp = _post(client, test_user, {"effective_from": "2026-08-01", "blocks": SHORT, **RETRO_REASON})
        assert resp.status_code == 201, resp.text
        assert resp.json()["adjusted_time_entries"] == 3
        [summary] = reclamp_logs(db, test_user, summary=True)
        assert summary.new_note.startswith("Arbeitszeit-Änderung ab 01.08.2026: 3 Einträge neu berechnet")

    def test_future_change_without_entries_writes_exactly_one_summary(self, client, db, test_user, test_admin):
        """P20: auch ohne Einträge, Abwesenheiten oder Blöcke."""
        resp = _post(client, test_user, {"effective_from": "2026-11-02", "weekly_hours": 25})
        assert resp.status_code == 201, resp.text
        [summary] = reclamp_logs(db, test_user, summary=True)
        assert summary.changed_by == test_admin.id
        assert summary.new_note == (
            "Arbeitszeit-Änderung ab 02.11.2026: 0 Einträge neu berechnet, Δ +0 Min, Saldo Δ +0 Min "
            "· Puffer 15 Min · Vertrag: 40,0 h/Woche (gleichmäßig, 5 Tage) → 25,0 h/Woche (gleichmäßig, 5 Tage)")
        assert reclamp_logs(db, test_user, summary=False) == []

    def test_entry_rows_name_a_deviating_stored_grace(self, client, db, test_user):
        set_grace(db, 10)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        e3 = entry(db, test_user, MONDAYS[3], t(7, 45), t(12), raw_start=t(7, 30))
        entry(db, test_user, MONDAYS[1], t(8), t(12))
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:30")], **TUE_THU)
        assert _post(client, test_user, {"effective_from": "2026-09-01", "blocks": week,
                                         **RETRO_REASON}).status_code == 201
        [row] = reclamp_logs(db, test_user, summary=False)
        assert row.time_entry_id == e3.id
        assert " · Puffer 15 → 10 Min" in row.new_note
        [summary] = reclamp_logs(db, test_user, summary=True)
        assert " · Puffer 10 Min · " in summary.new_note

    def test_put_message_names_the_new_button(self, client, test_user):
        resp = client.put(f"/api/admin/users/{test_user.id}", json={"weekly_hours": 30})
        assert resp.status_code == 400, resp.text
        assert "„Arbeitszeit anpassen…“" in resp.json()["detail"]

    def test_anchor_lock_is_taken_before_the_reclamp(self, client, db, test_user, monkeypatch):
        calls = []
        real_lock = admin_users_router.lock_user_row
        real_run = wh_change_service.run_change
        monkeypatch.setattr(admin_users_router, "lock_user_row",
                            lambda *a, **k: calls.append("lock") or real_lock(*a, **k))
        monkeypatch.setattr(wh_change_service, "run_change",
                            lambda *a, **k: calls.append("run") or real_run(*a, **k))
        assert _post(client, test_user, {"effective_from": "2026-11-02", "weekly_hours": 30}).status_code == 201
        assert calls == ["lock", "run"]


class TestResetOfChange:
    """P13/11.2 (Anlege-Seite): ``reset_of_change_id`` — der Body muss dem
    Vorgänger-Snapshot der zurückgesetzten Zeile entsprechen, sonst 409; die
    Sammelzeile nennt die Rücksetzung (10.2). Den Body baut hier der
    Server-Helfer ``reset_body`` (wie die ``delete-preview``, Task 11)."""

    def _reset(self, db, user, change_id, predecessor_day):
        predecessor = calculation_service.get_schedule_for_date(db, user, predecessor_day)
        return wh_change_service.reset_body(predecessor, date(2026, 10, 8), change_id)

    def test_uniform_reset_creates_a_new_row_with_the_predecessor_snapshot(self, client, db, test_user):
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        assert resp.status_code == 201, resp.text
        body = self._reset(db, test_user, resp.json()["id"], date(2026, 8, 31))
        assert body["weekly_hours"] == 40.0 and body["remove_legacy_window"] is True
        reset = _post(client, test_user, body)
        assert reset.status_code == 201, reset.text
        assert (reset.json()["weekly_hours"], reset.json()["blocks"]) == (40.0, None)
        summaries = reclamp_logs(db, test_user, summary=True)
        assert len(summaries) == 2
        parsed = reclamp_audit.parse_summary_note(summaries[-1].new_note)
        assert (parsed.effective_from, parsed.reset_of, parsed.shortening) == (
            date(2026, 10, 8), date(2026, 9, 1), False)

    def test_changed_body_is_409_and_writes_nothing(self, client, db, test_user):
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30})
        body = self._reset(db, test_user, resp.json()["id"], date(2026, 8, 31))
        conflict = _post(client, test_user, {**body, "weekly_hours": 39})
        assert (conflict.status_code, conflict.json()["detail"]) == (409, admin_users_router.RESET_CONFLICT_DETAIL)
        db.expire_all()
        assert db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == test_user.id).count() == 2
        assert len(reclamp_logs(db, test_user, summary=True)) == 1

    def test_reset_to_blocks(self, client, db, test_user):
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT})
        assert resp.status_code == 201, resp.text
        body = self._reset(db, test_user, resp.json()["id"], date(2026, 8, 31))
        assert body["blocks"] == ANNA_WEEK
        reset = _post(client, test_user, body)
        assert reset.status_code == 201, reset.text
        assert reset.json()["blocks"] == ANNA_WEEK

    def test_reset_brings_a_legacy_window_back(self, client, db, test_user):
        """Der Schreibweg nimmt kein Altfenster an — der Server trägt es aus dem
        Vorgänger-Snapshot selbst nach (``_target_blocks``)."""
        legacy = legacy_week(mon=("08:00", "17:00"))
        add_row(db, test_user, date(2026, 1, 1), weekly_hours=40, blocks=legacy)
        resp = _post(client, test_user, {"effective_from": "2026-09-01", "weekly_hours": 30,
                                         "remove_legacy_window": True})
        assert (resp.status_code, resp.json()["blocks"]) == (201, None), resp.text
        body = self._reset(db, test_user, resp.json()["id"], date(2026, 8, 31))
        assert "blocks" not in body and "remove_legacy_window" not in body
        reset = _post(client, test_user, body)
        assert reset.status_code == 201, reset.text
        assert reset.json()["blocks"] == legacy


class TestOvertimeHistoryParity:
    def test_history_matches_account_under_the_cutoff_after_reclamp(self, client, db, test_user):
        """Spec 17.5 / #313: nach der Neukappung bleibt ``get_overtime_history`` unter
        dem Saldo-Stichtag bitgleich zu ``get_overtime_account`` (Pflichtinvariante
        aus test_saldo_cutoff.py) — beide lesen die neu gekappten Einträge und die
        nachgezogenen Abwesenheiten."""
        _anna(db, test_user)
        assert _post(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT,
                                         **RETRO_REASON}).status_code == 201
        db.expire_all()
        user = db.get(User, test_user.id)
        cutoff = calculation_service.get_soll_cutoff_date(db, user)
        history = calculation_service.get_overtime_history(db, user, 2026, 10, cutoff_date=cutoff)
        last = max(history)  # (2026, 10) — der laufende Monat, vom Stichtag getrimmt
        assert last == (2026, 10)
        for year, month in ((2026, 9), last):
            assert history[(year, month)] == calculation_service.get_overtime_account(
                db, user, year, month, cutoff_date=cutoff), (year, month)


class TestAuditAfterAnonymisation:
    """Spec 17.5 ``test_reclamp_audit``: ``wh_reclamp``- und ``credit_override``-Zeilen
    tragen ``row_hash`` (#121). Beide Anonymisierungspfade schreiben Protokollnotizen
    über die Objektschicht um (1.18.1) — danach meldet verify-integrity weiter keine
    manipulierte Zeile."""

    def _reclamp_and_recognize(self, client, db, user):
        _anna(db, user)
        assert _post(client, user, {"effective_from": "2026-09-01", "blocks": SHORT,
                                    **RETRO_REASON}).status_code == 201
        cut = db.query(TimeEntry).filter(
            TimeEntry.user_id == user.id, TimeEntry.tenant_id == DEFAULT_TENANT_ID,
            TimeEntry.date == MONDAYS[1], TimeEntry.start_time == t(15)).one()
        assert cut.uncredited_minutes == 0 and cut.end_time == t(17, 15)  # Hülle gekürzt → anerkennbar
        resp = client.post(f"/api/admin/time-entries/{cut.id}/credit-override")
        assert resp.status_code == 200, resp.text
        sources = {r.source for r in db.query(TimeEntryAuditLog).filter(
            TimeEntryAuditLog.user_id == user.id, TimeEntryAuditLog.tenant_id == DEFAULT_TENANT_ID)}
        assert {"wh_reclamp", "credit_override"} <= sources

    def _assert_intact(self, client):
        report = client.get("/api/admin/audit/verify-integrity").json()
        assert (report["tampered"], report["intact"]) == (0, True), report["tampered_ids"]

    def test_after_user_anonymisation(self, client, db, test_user):
        self._reclamp_and_recognize(client, db, test_user)
        test_user.is_active = False   # ohne deactivated_at: Legacy-Zweig, keine 14-Tage-Sperrfrist
        db.commit()
        resp = client.post(f"/api/admin/users/{test_user.id}/anonymize")
        assert resp.status_code == 200, resp.text
        self._assert_intact(client)

    def test_after_tenant_anonymisation(self, client, db, test_user, default_tenant):
        self._reclamp_and_recognize(client, db, test_user)
        lifecycle_service.anonymize_tenant(db, default_tenant)
        self._assert_intact(client)
