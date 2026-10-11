"""Spec 11.1/11.3: Vorschau per POST — untypisiert, nie 422 beim Tippen, rollt
immer zurück, protokolliert nie."""
import re
import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.models import Absence, AbsenceType, TimeEntry, TimeEntryAuditLog, User, UserRole, WorkingHoursChange
from app.models.tenant import Tenant
from app.routers.admin_users import PREVIEW_DATE_MISSING, RESET_CONFLICT_DETAIL
from app.schemas.working_hours_change import EFFECTIVE_FROM_RANGE_DETAIL, WorkingHoursChangeCreate
from app.services import calculation_service, wh_change_service
from tests.test_endpoints import test_app
from tests.wh_change_helpers import (
    ANNA_WEEK, MONDAYS, absence, add_row, admin_client, entry, freeze, t, with_pauses,
)
from tests.work_blocks_fixtures import block_week

TUE_THU = dict(tue=[("08:00", "12:00")], thu=[("08:00", "12:00")])
SHORT = block_week(mon=[("08:00", "12:00"), ("15:00", "17:00")], **TUE_THU)
LONGER_PAUSED = with_pauses(block_week(mon=[("08:00", "12:00"), ("15:00", "19:00")], **TUE_THU), mon=60)


@pytest.fixture
def client(db, test_admin, monkeypatch):
    freeze(monkeypatch)
    c = admin_client(db, test_admin)
    yield c
    test_app.dependency_overrides.clear()


def _preview(client, user, body):
    resp = client.post(f"/api/admin/users/{user.id}/working-hours-changes/preview", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _anna(db, user, *, afternoon_14=None, afternoon_21=None):
    add_row(db, user, date(2026, 3, 1), week=ANNA_WEEK)
    absence(db, user, MONDAYS[0], AbsenceType.VACATION, 7.0)
    for d in MONDAYS[1:]:
        entry(db, user, d, t(8), t(12))
        if d == MONDAYS[1] and afternoon_14:
            entry(db, user, d, t(15), afternoon_14[0], raw_end=afternoon_14[1])
        elif d == MONDAYS[2] and afternoon_21:
            entry(db, user, d, t(15), afternoon_21[0], raw_end=afternoon_21[1])
        else:
            entry(db, user, d, t(15), t(18), credit_override=(d == MONDAYS[3]))


def _week_with(mon):
    week = block_week(**TUE_THU)
    week[0] = mon
    return week


class TestUnfinishedInput:
    """Review Focus 1: unfertige Eingaben kommen als blocked_reason, nie als 422."""

    @pytest.mark.parametrize("mon, message", [
        ({"blocks": [{"start": "", "end": "12:00"}], "pause_minutes": 0}, "Mo, Block 1: Uhrzeit im Format HH:MM angeben."),
        ({"blocks": [{"start": "08:00", "end": "12:00"}], "pause_minutes": None}, "Mo: Pause angeben (0, wenn keine)."),
        ({"blocks": [{"start": "08:07", "end": "12:00"}], "pause_minutes": 0},
         "Mo, Block 1: Uhrzeiten im 5-Minuten-Raster (z. B. 08:05)."),
        ({"blocks": [{"start": "08:00", "end": "12:00"}], "pause_minutes": 240},
         "Mo: Pause muss kürzer sein als die Gesamtzeit der Blöcke."),
        ({"blocks": [{"start": 8, "end": "12:00"}], "pause_minutes": 0}, "Mo, Block 1, Beginn: ungültiger Wert."),
    ])
    def test_unfinished_blocks(self, client, test_user, mon, message):
        body = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": _week_with(mon)})
        assert body["blocked_reason"] == message
        assert body["affected_time_entries"] == 0

    @pytest.mark.parametrize("raw", [
        {}, {"effective_from": "2026-13-01", "weekly_hours": 30}, {"weekly_hours": 30},
        # ISO-Formen, die ``date.fromisoformat`` liest, das Speichern aber ablehnt,
        # und ein Datum, das keine Zeichenkette ist.
        {"effective_from": "20260901", "weekly_hours": 30}, {"effective_from": 20260901, "weekly_hours": 30},
        # Kein JSON-Objekt (untypisierter Body) — auch das ist kein 422.
        ["2026-09-01"],
    ])
    def test_missing_or_broken_date(self, client, test_user, raw):
        assert _preview(client, test_user, raw)["blocked_reason"] == PREVIEW_DATE_MISSING

    def test_without_body(self, client, test_user):
        resp = client.post(f"/api/admin/users/{test_user.id}/working-hours-changes/preview")
        assert resp.status_code == 200, resp.text
        assert resp.json()["blocked_reason"] == PREVIEW_DATE_MISSING

    # Review Task 10: Chrome/Edge melden beim Tippen der Jahreszahl Zwischenwerte
    # (0002-…, 0020-…, 0202-…) als vollständiges Datum. ``date.fromisoformat``
    # nimmt sie an — ohne Grenze lief ``run_change`` über ~22.000 Monate (73 s)
    # bzw. endete in ``OverflowError`` (500).
    @pytest.mark.parametrize("value", ["0202-09-01", "0001-01-01", "0020-09-01", "1999-12-31", "2101-01-01"])
    def test_implausible_year_is_a_missing_date(self, client, test_user, monkeypatch, value):
        def _never(*args, **kwargs):
            raise AssertionError("run_change darf bei einem unplausiblen Datum nicht laufen")

        monkeypatch.setattr(wh_change_service, "run_change", _never)
        body = _preview(client, test_user, {"effective_from": value, "weekly_hours": 30})
        assert body["blocked_reason"] == PREVIEW_DATE_MISSING
        assert (body["affected_time_entries"], body["is_retroactive"]) == (0, False)

    @pytest.mark.parametrize("value", ["0202-09-01", "0001-01-01", "1999-12-31", "2101-01-01"])
    def test_saving_an_implausible_year_is_a_german_422(self, client, db, test_user, value):
        resp = client.post(f"/api/admin/users/{test_user.id}/working-hours-changes",
                           json={"effective_from": value, "weekly_hours": 30})
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"] == EFFECTIVE_FROM_RANGE_DETAIL
        assert db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == test_user.id).count() == 0

    def test_range_bounds_are_inclusive(self):
        for d in (date(2000, 1, 1), date(2100, 12, 31)):
            assert WorkingHoursChangeCreate(effective_from=d, weekly_hours=30).effective_from == d
        for d in (date(1999, 12, 31), date(2101, 1, 1)):
            with pytest.raises(ValidationError, match=re.escape(EFFECTIVE_FROM_RANGE_DETAIL)):
                WorkingHoursChangeCreate(effective_from=d, weekly_hours=30)

    def test_old_get_preview_is_gone(self, client, test_user):
        resp = client.get(f"/api/admin/users/{test_user.id}/working-hours-changes/preview"
                          f"?effective_from=2026-09-01&weekly_hours=30")
        assert resp.status_code == 405


class TestImpactFields:
    def test_first_state(self, client, db, test_user):
        _anna(db, test_user)
        body = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT})
        assert (body["is_retroactive"], body["period_start"], body["period_end"]) == (True, "2026-09-01", "2026-10-08")
        assert (body["grace_minutes"], body["changed_weekdays"], body["affected_time_entries"]) == (15, [0], 3)
        assert body["time_entry_months"] == [
            {"month": "2026-09", "entries": 2, "net_before": 6.0, "net_after": 4.5},
            {"month": "2026-10", "entries": 1, "net_before": 3.0, "net_after": 2.25},
        ]
        assert [s["reason"] for s in body["skipped_time_entries"]] == ["credit_override"]
        assert (body["target_delta_hours"], body["credited_delta_hours"], body["saldo_delta_hours"]) == (-4.0, -2.25, 1.75)
        assert (body["is_shortening"], body["shortening_reasons"], body["earliest_lossless_date"]) == (
            True, ["entries"], "2026-10-08")
        assert (body["lost_credited_hours"], body["affected_absences"]) == (2.25, 1)
        assert body["blocks_current"] == ANNA_WEEK and body["blocks_new"] == SHORT
        assert body["time_entry_changes"][0]["new_end"] == "17:15:00"
        assert body["overtime_after"] - body["overtime_before"] == pytest.approx(1.75)
        assert body["milog_warning"] == [wh_change_service.MILOG_GENERAL_WARNING]

    def test_preview_writes_and_logs_nothing(self, client, db, test_user):
        _anna(db, test_user)
        stale = entry(db, test_user, date(2026, 10, 6), t(8), None)

        def state():
            db.expire_all()
            return (
                sorted((str(e.id), e.start_time, e.end_time, e.raw_start_time, e.raw_end_time,
                        e.uncredited_minutes, e.clamp_grace_minutes)
                       for e in db.query(TimeEntry).filter(TimeEntry.user_id == test_user.id)),
                sorted(float(a.hours) for a in db.query(Absence).filter(Absence.user_id == test_user.id)),
                db.query(WorkingHoursChange).filter(WorkingHoursChange.user_id == test_user.id).count(),
                db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.user_id == test_user.id).count(),
            )

        before = state()
        body = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT})
        assert body["stale_entries_closed"] == 1
        assert state() == before
        db.refresh(stale)
        assert stale.end_time is None

    def test_second_preview_at_the_earliest_date_is_lossless(self, client, db, test_user):
        _anna(db, test_user)
        first = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT})
        second = _preview(client, test_user, {"effective_from": first["earliest_lossless_date"], "blocks": SHORT})
        assert (second["is_shortening"], second["affected_time_entries"]) == (False, 0)

    def test_milog_warning_with_agreed_monthly_hours(self, client, db, test_user):
        _anna(db, test_user)
        test_user.agreed_monthly_hours = 65.0
        db.commit()
        body = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": SHORT})
        assert body["milog_warning"] == [wh_change_service.MILOG_ACCOUNT_WARNING, wh_change_service.MILOG_GENERAL_WARNING]

    def test_lengthening_lists_the_not_extendable_entry(self, client, db, test_user):
        _anna(db, test_user, afternoon_14=(t(18, 15), None), afternoon_21=(t(18, 15), t(18, 30)))
        body = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": LONGER_PAUSED})
        assert (body["is_shortening"], body["milog_warning"], body["not_extendable_count"]) == (False, [], 1)
        [flag] = body["not_extendable_entries"]
        assert (flag["date"], flag["not_extendable"], flag["old_end"]) == ("2026-09-14", "end", "18:15:00")

    def test_plan_notices_come_with_the_preview(self, client, test_user):
        body = _preview(client, test_user, {"effective_from": "2026-11-02",
                                            "blocks": block_week(mon=[("07:00", "12:00"), ("12:10", "17:10")])})
        assert ("Mo: geplant 10:00 h Arbeit, eingeplante Pausen 0 Min – nach § 4 ArbZG sind mindestens 45 Minuten "
                "nötig.") in body["block_break_notices"]
        assert body["blocked_reason"] is None

    def test_reset_body_that_no_longer_matches_is_blocked(self, client, db, test_user):
        add_row(db, test_user, date(2026, 1, 1), weekly_hours=40)
        later = add_row(db, test_user, date(2026, 9, 1), weekly_hours=30)
        body = _preview(client, test_user, {"effective_from": "2026-10-08", "use_daily_schedule": False,
                                            "weekly_hours": 39, "work_days_per_week": 5,
                                            "reset_of_change_id": str(later.id)})
        assert body["blocked_reason"] == RESET_CONFLICT_DETAIL

    def test_foreign_or_unknown_reset_is_blocked_with_one_text(self, client, db, test_user):
        """Review Task 10 (F-026, kein Existenz-Leak): eine Rücksetzung auf die
        Zeile einer anderen Person, eines anderen Mandanten oder eine unbekannte
        ID ist ``blocked_reason`` (kein 404) — überall derselbe Text."""
        add_row(db, test_user, date(2026, 1, 1), weekly_hours=40)
        colleague = User(username="kollegin", email="kollegin@example.com", password_hash="x",
                         first_name="K", last_name="T", role=UserRole.EMPLOYEE, weekly_hours=40.0,
                         vacation_days=30, work_days_per_week=5, is_active=True, tenant_id=test_user.tenant_id)
        other_tenant_id = uuid.UUID("00000000-0000-0000-0000-0000000000fe")
        db.add(Tenant(id=other_tenant_id, name="Fremd", slug="fremd", is_active=True, mode="single"))
        stranger = User(username="fremd", email="fremd@example.com", password_hash="x",
                        first_name="F", last_name="T", role=UserRole.EMPLOYEE, weekly_hours=40.0,
                        vacation_days=30, work_days_per_week=5, is_active=True, tenant_id=other_tenant_id)
        db.add_all([colleague, stranger])
        db.commit()
        colleague_row = add_row(db, colleague, date(2026, 9, 1), weekly_hours=30)
        stranger_row = WorkingHoursChange(user_id=stranger.id, tenant_id=other_tenant_id,
                                          effective_from=date(2026, 9, 1), weekly_hours=30,
                                          use_daily_schedule=False, work_days_per_week=5)
        db.add(stranger_row)
        db.commit()
        db.refresh(stranger_row)
        entry(db, test_user, date(2026, 9, 15), t(8), t(12))

        texts = []
        for reset_id in (colleague_row.id, stranger_row.id, uuid.uuid4()):
            body = _preview(client, test_user, {"effective_from": "2026-09-01", "use_daily_schedule": False,
                                                "weekly_hours": 40, "work_days_per_week": 5,
                                                "reset_of_change_id": str(reset_id)})
            assert body["affected_time_entries"] == 0
            texts.append(body["blocked_reason"])
        assert texts == ["Stundenänderung nicht gefunden"] * 3

    def test_pure_block_shift_is_a_change_unchanged_blocks_are_not(self, client, db, test_user):
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        entry(db, test_user, date(2026, 9, 15), t(8), t(12))
        shifted = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("09:00", "13:00")],
                             thu=[("08:00", "12:00")])
        body = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": shifted})
        assert (body["changed_weekdays"], body["affected_time_entries"]) == ([1], 1)
        same = _preview(client, test_user, {"effective_from": "2026-09-01", "blocks": ANNA_WEEK})
        assert (same["changed_weekdays"], same["affected_time_entries"], same["is_shortening"]) == ([], 0, False)

    def test_saturday_effective_date(self, client, db, test_user):
        """Review Focus 3."""
        _anna(db, test_user)
        body = _preview(client, test_user, {"effective_from": "2026-08-01", "blocks": SHORT})
        assert (body["period_start"], body["affected_time_entries"], body["earliest_lossless_date"]) == (
            "2026-08-01", 3, "2026-10-08")


class TestPreviewSaveParity:
    """Review Task 10 / Spec 9.3 Schritt 10: Vorschau und Speichern rechnen
    denselben Zustand — der Spiegel der User-Zeile kommt erst NACH der
    Klassifikation. Und der Commit verschiebt das Soll buchungsfreier Tage vor
    der Basis-Zeile nicht ungeschützt: Tage, die das Überstundenkonto schon
    zählt (ab dem Monatsersten des ältesten Eintrags), aber keine Verlaufszeile
    deckt, fielen nach dem Spiegel auf den NEUEN Vertrag zurück."""

    # Gleiche Wochensumme, anders verteilt: im Wirkungsbereich (15.09.–07.10.)
    # gleichen sich drei Montage (−2 h) und drei Freitage (+2 h) aus.
    BODY = {"effective_from": "2026-09-15", "use_daily_schedule": True, "hours_monday": 6,
            "hours_tuesday": 8, "hours_wednesday": 8, "hours_thursday": 8, "hours_friday": 10}

    @staticmethod
    def _overtime(db, user):
        db.expire_all()
        user = db.query(User).filter(User.id == user.id).one()
        cutoff = calculation_service.get_soll_cutoff_date(db, user)
        return float(calculation_service.get_overtime_account(db, user, 2026, 10, cutoff_date=cutoff))

    @pytest.mark.parametrize("oldest", [date(2026, 9, 21), date(2026, 8, 21)])
    def test_preview_and_save_agree_and_the_commit_matches_the_preview(self, client, db, test_user, oldest):
        entry(db, test_user, oldest, t(8), t(16))
        before = self._overtime(db, test_user)
        preview = _preview(client, test_user, self.BODY)
        resp = client.post(f"/api/admin/users/{test_user.id}/working-hours-changes", json=self.BODY)
        assert preview["is_shortening"] == (resp.status_code == 400)
        assert resp.status_code == 201, resp.text
        assert self._overtime(db, test_user) == pytest.approx(before + preview["saldo_delta_hours"])

    def test_existing_history_classifies_like_the_preview(self, client, db, test_user):
        """Mit Verlauf entsteht keine Basis-Zeile; die Tage vor der ältesten Zeile
        (hier 01.–13.09.) lösen weiter auf die User-Zeile auf. Spiegelte das
        Speichern sie schon in Schritt 4, sah seine Klassifikation dort den neuen
        Vertrag (400 „Rückwirkende Verkürzung …"), die Vorschau nicht — der Dialog
        bot das Schutzpaket nie an, das Speichern verlangte es."""
        add_row(db, test_user, date(2026, 9, 14), weekly_hours=40)
        entry(db, test_user, date(2026, 9, 21), t(8), t(16))
        preview = _preview(client, test_user, self.BODY)
        resp = client.post(f"/api/admin/users/{test_user.id}/working-hours-changes", json=self.BODY)
        assert preview["is_shortening"] == (resp.status_code == 400)
        assert resp.status_code == 201, resp.text
        db.expire_all()
        user = db.query(User).filter(User.id == test_user.id).one()
        assert (user.use_daily_schedule, float(user.hours_monday)) == (True, 6.0)  # Schritt 10 spiegelt weiter
