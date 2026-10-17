"""Spec 9.3–9.5: der eine Rechenpfad der Rückwirkung und seine Klassifikation.

„heute" = Do 08.10.2026 10:00 (Spec 12.1). Jeder Test ruft ``run_change`` direkt
und rollt danach nicht zurück — die Fixture-Session wird je Test verworfen."""
from datetime import date, time, timedelta
from decimal import Decimal
from uuid import uuid4

from app.models import AbsenceType, TimeEntryAuditLog, YearCarryover
from app.schemas.working_hours_change import WorkingHoursChangeDelete
from app.services import calculation_service, wh_change_service as svc
from tests.conftest import DEFAULT_TENANT_ID
from tests.wh_change_helpers import (
    ANNA_WEEK, EFF, MONDAYS, RETRO_REASON, TODAY, absence, add_row, change_row, entry, freeze, set_grace,
    t, with_pauses,
)
from tests.work_blocks_fixtures import block_week, legacy_week

TUE_THU = dict(tue=[("08:00", "12:00")], thu=[("08:00", "12:00")])
SHORT = block_week(mon=[("08:00", "12:00"), ("15:00", "17:00")], **TUE_THU)
LONGER = block_week(mon=[("08:00", "12:00"), ("15:00", "19:00")], **TUE_THU)
LONGER_PAUSED = with_pauses(LONGER, mon=60)
TOMORROW = TODAY + timedelta(days=1)


def _run(db, user, admin, eff=EFF, **row):
    return svc.run_change(db, user, admin_id=admin.id, effective_from=eff,
                          apply=lambda: db.add(change_row(user, eff, **row)))


def _anna(db, user, *, afternoon_14=None, afternoon_21=None, vacation=True):
    """Spec 12.1: Montage im Wirkungsbereich je 08–12 und 15–18; 28.09.
    nachmittags anerkannt; 07.09. Urlaub (7 h)."""
    add_row(db, user, date(2026, 3, 1), week=ANNA_WEEK)
    if vacation:
        absence(db, user, MONDAYS[0], AbsenceType.VACATION, 7.0)
    for d in MONDAYS[1:]:
        entry(db, user, d, t(8), t(12))
        if d == MONDAYS[1] and afternoon_14:
            entry(db, user, d, t(15), afternoon_14[0], raw_end=afternoon_14[1])
        elif d == MONDAYS[2] and afternoon_21:
            entry(db, user, d, t(15), afternoon_21[0], raw_end=afternoon_21[1])
        else:
            entry(db, user, d, t(15), t(18), credit_override=(d == MONDAYS[3]))


class TestSpecStates:
    def test_first_state_shortening_by_entries(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        _anna(db, test_user)
        impact = _run(db, test_user, test_admin, week=SHORT)
        assert [(c.date, c.old_net, c.new_net) for c in impact.reclamp.changed] == [
            (MONDAYS[1], Decimal("3.00"), Decimal("2.25")),
            (MONDAYS[2], Decimal("3.00"), Decimal("2.25")),
            (MONDAYS[4], Decimal("3.00"), Decimal("2.25")),
        ]
        assert [(s.date, s.reason) for s in impact.reclamp.skipped] == [(MONDAYS[3], "credit_override")]
        assert (impact.target_delta, impact.credited_delta, impact.saldo_delta) == (
            Decimal("-4"), Decimal("-2.25"), Decimal("1.75"))
        assert impact.shortening_reasons == ["entries"]
        assert impact.earliest_lossless_date == TODAY
        assert [(a.date, a.old_hours, a.new_hours) for a in impact.absences] == [
            (MONDAYS[0], Decimal("7.00"), Decimal("6.00"))]
        assert impact.months == [
            {"month": "2026-09", "entries": 2, "net_before": 6.0, "net_after": 4.5},
            {"month": "2026-10", "entries": 1, "net_before": 3.0, "net_after": 2.25},
        ]
        assert (impact.changed_weekdays, impact.grace) == ([0], 15)

    def test_second_state_lengthening_with_equal_target(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        _anna(db, test_user, afternoon_14=(t(18, 15), None), afternoon_21=(t(18, 15), t(18, 30)))
        impact = _run(db, test_user, test_admin, week=LONGER_PAUSED)
        assert [(c.date, c.old_net, c.new_net) for c in impact.reclamp.changed] == [
            (MONDAYS[2], Decimal("3.25"), Decimal("3.50"))]
        assert [(c.date, c.not_extendable, c.old_end) for c in impact.reclamp.flagged] == [
            (MONDAYS[1], "end", t(18, 15))]
        assert (impact.target_delta, impact.credited_delta, impact.saldo_delta) == (
            Decimal("0"), Decimal("0.25"), Decimal("0.25"))
        assert (impact.shortening_reasons, impact.earliest_lossless_date, impact.absences) == ([], None, [])

    def test_third_state_target_raise_is_a_shortening(self, db, test_user, test_admin, monkeypatch):
        """19.1 Nr. 1 Pflichtfall: kein Eintrag verliert, das Konto sinkt."""
        freeze(monkeypatch)
        _anna(db, test_user, afternoon_14=(t(18, 15), None), afternoon_21=(t(18, 15), t(18, 30)))
        impact = _run(db, test_user, test_admin, week=LONGER)
        assert (impact.target_delta, impact.credited_delta, impact.saldo_delta) == (
            Decimal("4"), Decimal("0.25"), Decimal("-3.75"))
        assert (impact.shortening_reasons, impact.earliest_lossless_date) == (["saldo"], TODAY)
        assert [(a.old_hours, a.new_hours) for a in impact.absences] == [(Decimal("7.00"), Decimal("8.00"))]


class TestSaldoCriterion:
    def test_minus_one_hundredth_is_a_shortening_zero_is_not(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 1, 1), day_hours=(8, 8, 8, 8, 8))
        oct5 = date(2026, 10, 5)
        impact = _run(db, test_user, test_admin, eff=oct5, day_hours=(8.01, 8, 8, 8, 8))
        assert (impact.saldo_delta, impact.shortening_reasons) == (Decimal("-0.01"), ["saldo"])
        db.rollback()
        impact = _run(db, test_user, test_admin, eff=oct5, day_hours=(8, 8, 8, 8, 8.01))
        assert (impact.saldo_delta, impact.shortening_reasons) == (Decimal("0"), [])

    def test_target_drop_with_sick_day_without_work(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        absence(db, test_user, MONDAYS[1], AbsenceType.SICK, 8.0)
        impact = _run(db, test_user, test_admin, weekly_hours=30)
        assert [(a.new_hours, a.f1_clamped) for a in impact.absences] == [(Decimal("6.00"), False)]
        assert impact.shortening_reasons == []

    def test_closed_year_loss_counts_even_if_the_total_gains(self, db, test_user, test_admin, monkeypatch):
        """Gewinn im laufenden Jahr, Verlust im abgeschlossenen Vorjahr → Verkürzung."""
        freeze(monkeypatch)
        test_user.first_work_day, test_user.last_work_day = date(2025, 1, 1), date(2026, 1, 12)
        db.add(YearCarryover(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, year=2026,
                             overtime_hours=Decimal("0"), vacation_days=Decimal("0"), source="year_closing"))
        db.commit()
        add_row(db, test_user, date(2025, 1, 1), day_hours=(8, 8, 8, 8, 8))
        impact = _run(db, test_user, test_admin, eff=date(2025, 12, 29), day_hours=(12, 8, 8, 0, 8))
        assert impact.saldo_delta == Decimal("4")
        assert (impact.shortening_reasons, impact.shortening_closed_years) == (["saldo"], [2025])
        assert svc.protection_error(impact, WorkingHoursChangeDelete(**RETRO_REASON), deleting=False,
                                    reset_offered=False) == svc.closed_year_detail([2025])

    def test_two_closed_years_name_the_larger_one(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        test_user.first_work_day = date(2024, 1, 1)
        for year in (2025, 2026):
            db.add(YearCarryover(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, year=year,
                                 overtime_hours=Decimal("0"), vacation_days=Decimal("0"), source="year_closing"))
        db.commit()
        add_row(db, test_user, date(2024, 1, 1), day_hours=(8, 8, 8, 8, 8))
        impact = _run(db, test_user, test_admin, eff=date(2024, 6, 3), day_hours=(9, 8, 8, 8, 8))
        assert impact.shortening_closed_years == [2024, 2025]
        assert svc.closed_year_detail(impact.shortening_closed_years) == (
            "Rückwirkende Verkürzung in das abgeschlossene Jahr 2025 ist gesperrt. "
            "Bitte die Änderung frühestens ab 01.01.2026 wirksam werden lassen.")


class TestAbsenceCreditCriterion:
    def test_regularly_clamped_mixed_day_with_target_drop_is_neutral(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        absence(db, test_user, MONDAYS[1], AbsenceType.SICK, 4.0)
        entry(db, test_user, MONDAYS[1], t(8), t(12), grace=None)
        impact = _run(db, test_user, test_admin, weekly_hours=30)
        assert [(a.new_hours, a.f1_clamped, a.credit_reduction) for a in impact.absences] == [
            (Decimal("2.00"), True, False)]
        assert (impact.credit_reductions, impact.shortening_reasons) == ([], [])

    def test_pre_1_18_double_credit_on_an_unchanged_weekday(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 1, 1), day_hours=(8, 8, 8, 8, 8))
        absence(db, test_user, MONDAYS[1], AbsenceType.SICK, 8.0)
        entry(db, test_user, MONDAYS[1], t(8), t(12), grace=None)
        impact = _run(db, test_user, test_admin, day_hours=(8, 8, 8, 8, 4))
        assert [(a.date, a.old_hours, a.new_hours) for a in impact.credit_reductions] == [
            (MONDAYS[1], Decimal("8.00"), Decimal("4.00"))]
        assert (impact.shortening_reasons, impact.earliest_lossless_date) == (["absence_credit"], TODAY)

    def test_entry_gaining_on_a_mixed_day(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        set_grace(db, 0)
        add_row(db, test_user, date(2026, 3, 1), week=block_week(mon=[("08:00", "12:00"), ("14:00", "18:00")]))
        absence(db, test_user, MONDAYS[1], AbsenceType.SICK, 4.0)
        entry(db, test_user, MONDAYS[1], t(8), t(13), uncredited=60, grace=0)
        impact = _run(db, test_user, test_admin, week=block_week(mon=[("08:00", "13:00"), ("15:00", "18:00")]))
        assert [(c.old_net, c.new_net) for c in impact.reclamp.changed] == [(Decimal("4.00"), Decimal("5.00"))]
        assert [(a.old_hours, a.new_hours) for a in impact.credit_reductions] == [(Decimal("4.00"), Decimal("3.00"))]
        assert (impact.saldo_delta, impact.shortening_reasons) == (Decimal("0"), ["absence_credit"])


class TestToday:
    """P1/9.5 (b): heute offener Tag, geschlossener Eintrag heute, kein Eintrag heute."""

    def test_target_raise_while_clocked_in(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        entry(db, test_user, TODAY, t(8), None)
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                          thu=[("08:00", "13:00")])
        impact = _run(db, test_user, test_admin, eff=TODAY, week=week)
        assert (impact.saldo_delta, impact.open_day_saldo_delta) == (Decimal("0"), Decimal("-1"))
        assert (impact.shortening_reasons, impact.earliest_lossless_date) == (["saldo"], TOMORROW)
        assert [(s.date, s.reason) for s in impact.reclamp.skipped] == [(TODAY, "open")]
        assert impact.open_entry_loses is False
        db.rollback()
        assert _run(db, test_user, test_admin, eff=TOMORROW, week=week).shortening_reasons == []

    def test_pause_compensation_while_clocked_in_is_no_shortening(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        entry(db, test_user, TODAY, t(8), None)
        week = with_pauses(block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                                      thu=[("08:00", "13:00")]), thu=60)
        assert _run(db, test_user, test_admin, eff=TODAY, week=week).shortening_reasons == []

    def test_open_entry_whose_hull_shrinks_loses(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        entry(db, test_user, TODAY, t(8), None)
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                          thu=[("08:00", "11:00")])
        impact = _run(db, test_user, test_admin, eff=TODAY, week=week)
        assert (impact.open_entry_loses, impact.shortening_reasons, impact.earliest_lossless_date) == (
            True, ["entries"], TOMORROW)

    def test_target_raise_with_a_closed_entry_today(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        entry(db, test_user, TODAY, t(8), t(9))
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                          thu=[("08:00", "13:00")])
        impact = _run(db, test_user, test_admin, eff=TODAY, week=week)
        assert (impact.saldo_delta, impact.shortening_reasons, impact.earliest_lossless_date) == (
            Decimal("-1"), ["saldo"], TOMORROW)

    def test_closed_entry_losing_today_moves_the_default_to_tomorrow(self, db, test_user, test_admin, monkeypatch):
        """Spec 17.5: geschlossener verlierender Eintrag heute → morgen (A + 1), auch
        wenn das Soll von heute mitsinkt und der Tagessaldo nicht fällt (H entfällt)."""
        freeze(monkeypatch, at=time(13, 0))
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        entry(db, test_user, TODAY, t(8), t(12, 15), raw_end=t(12, 30))
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                          thu=[("08:00", "11:00")])
        impact = _run(db, test_user, test_admin, eff=TODAY, week=week)
        assert [(c.date, c.old_net, c.new_net) for c in impact.reclamp.changed] == [
            (TODAY, Decimal("4.25"), Decimal("3.25"))]
        assert (impact.saldo_delta, impact.shortening_reasons, impact.earliest_lossless_date) == (
            Decimal("0"), ["entries"], TOMORROW)
        db.rollback()
        assert _run(db, test_user, test_admin, eff=TOMORROW, week=week).shortening_reasons == []

    def test_without_any_entry_today_the_default_is_today(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                          thu=[("08:00", "13:00")])
        impact = _run(db, test_user, test_admin, week=week)
        assert (impact.saldo_delta, impact.earliest_lossless_date) == (Decimal("-5"), TODAY)
        db.rollback()
        assert _run(db, test_user, test_admin, eff=TODAY, week=week).shortening_reasons == []

    def test_p25_earliest_reaches_the_next_change(self, db, test_user, test_admin, monkeypatch):
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        add_row(db, test_user, TODAY, week=ANNA_WEEK)
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "12:00")],
                          thu=[("08:00", "13:00")])
        impact = _run(db, test_user, test_admin, week=week)
        assert impact.earliest_lossless_date is None
        assert impact.earliest_lossless_note == (
            "Die Änderung liegt vollständig vor der Änderung ab 08.10.2026; "
            "nur rückwirkend mit Begründung oder abbrechen.")


class TestStaleEntriesAndGrace:
    def test_open_entry_of_a_past_day_is_closed_first_then_reclamped(self, db, test_user, test_admin, monkeypatch):
        """P23 (19.1 Nr. 5): geschlossen unter dem ALTEN Snapshot (Audit auto_close
        mit der handelnden Admin), danach regulär neu gekappt; das Schließen geht
        nicht in den Saldo ein."""
        freeze(monkeypatch)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        tuesday = date(2026, 10, 6)
        stale = entry(db, test_user, tuesday, t(8), None)
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:00")], tue=[("08:00", "11:00")],
                          thu=[("08:00", "12:00")])
        impact = _run(db, test_user, test_admin, week=week)
        assert impact.stale_closed == 1
        assert [(c.entry_id, c.old_end, c.new_end) for c in impact.reclamp.changed] == [
            (stale.id, t(12, 15), t(11, 15))]
        assert impact.reclamp.skipped == []
        assert impact.saldo_delta == Decimal("5")
        audit = db.query(TimeEntryAuditLog).filter(TimeEntryAuditLog.time_entry_id == stale.id,
                                                   TimeEntryAuditLog.source == "auto_close").one()
        assert audit.changed_by == test_admin.id

    def test_mass_reclamp_writes_the_current_grace(self, db, test_user, test_admin, monkeypatch):
        """E47/E79/E80: aktueller Puffer 10, gespeichert 15 — ein Eintrag verliert;
        alle geprüften Einträge geänderter Wochentage tragen danach 10."""
        freeze(monkeypatch)
        set_grace(db, 10)
        add_row(db, test_user, date(2026, 3, 1), week=ANNA_WEEK)
        e1 = entry(db, test_user, MONDAYS[1], t(8), t(12))
        e2 = entry(db, test_user, MONDAYS[2], t(15), t(18, 15), raw_end=t(18, 40))
        e3 = entry(db, test_user, MONDAYS[3], t(7, 45), t(12), raw_start=t(7, 30))
        e4 = entry(db, test_user, MONDAYS[4], t(8), t(12), grace=None)
        e5 = entry(db, test_user, date(2026, 9, 15), t(8), t(12))
        e6 = entry(db, test_user, MONDAYS[1], t(15), t(18), credit_override=True)
        week = block_week(mon=[("08:00", "12:00"), ("15:00", "18:30")], **TUE_THU)
        impact = _run(db, test_user, test_admin, week=week)
        assert sorted(c.entry_id for c in impact.reclamp.changed) == sorted([e2.id, e3.id])
        assert {c.entry_id: c.old_grace for c in impact.reclamp.changed} == {e2.id: 15, e3.id: 15}
        assert "entries" in impact.shortening_reasons
        assert [e.clamp_grace_minutes for e in (e1, e2, e3, e4, e5, e6)] == [10, 10, 10, 10, 15, 15]
        assert (e3.start_time, e3.raw_start_time) == (t(7, 50), t(7, 30))


def test_arbzg_findings_before_after_and_presence(db, test_user, test_admin, monkeypatch):
    freeze(monkeypatch)
    ten = [("07:00", "17:00")]
    add_row(db, test_user, date(2026, 3, 1), week=block_week(mon=ten, tue=ten, wed=ten, thu=ten, fri=ten))
    for offset in range(5):
        entry(db, test_user, MONDAYS[1] + timedelta(days=offset), t(7), t(17))
    eight = [("07:00", "15:00")]
    impact = _run(db, test_user, test_admin, week=block_week(mon=eight, tue=eight, wed=eight, thu=eight, fri=eight))
    assert impact.arbzg == {
        "days_over_10_credited_before": 0, "days_over_10_credited_after": 0, "days_over_10_presence": 0,
        "weeks_over_48_credited_before": 1, "weeks_over_48_credited_after": 0, "weeks_over_48_presence": 1,
    }


class TestArbzgFindingsEdgeWeeks:
    """P22: eine Kalenderwoche, die der Wirkungsbereich nur anschneidet, zählt
    über volle Mo–So wie ``presence_service`` — die Tage außerhalb ändert die
    Änderung nicht, sie gehen unverändert in „vorher" und „nachher" ein. Tage
    > 10 h zählen weiter nur im Wirkungsbereich."""
    TWELVE = [("06:00", "18:00")]
    EIGHT = [("06:00", "14:00")]

    def _setup(self, db, user):
        set_grace(db, 0)
        add_row(db, user, date(2026, 3, 1), week=block_week(
            mon=self.TWELVE, tue=self.TWELVE, wed=self.TWELVE, thu=self.TWELVE, fri=self.TWELVE))
        week_mon = date(2026, 9, 14)
        for offset in range(2):
            entry(db, user, week_mon + timedelta(days=offset), t(6), t(18), grace=0)
        for offset in range(2, 5):
            entry(db, user, week_mon + timedelta(days=offset), t(6), t(16), grace=0)

    def test_effective_date_mid_week(self, db, test_user, test_admin, monkeypatch):
        """Mo/Di 12 h liegen VOR dem Wirkungsdatum Mi 16.09.; Mi–Fr 10 h → 8 h:
        die Woche fällt von 54 h auf 48 h angerechnet, laut Stempel bleibt sie."""
        freeze(monkeypatch)
        self._setup(db, test_user)
        impact = _run(db, test_user, test_admin, eff=date(2026, 9, 16), week=block_week(
            mon=self.TWELVE, tue=self.TWELVE, wed=self.EIGHT, thu=self.EIGHT, fri=self.EIGHT))
        assert impact.arbzg == {
            "days_over_10_credited_before": 0, "days_over_10_credited_after": 0, "days_over_10_presence": 0,
            "weeks_over_48_credited_before": 1, "weeks_over_48_credited_after": 0, "weeks_over_48_presence": 1,
        }

    def test_next_change_mid_week(self, db, test_user, test_admin, monkeypatch):
        """Die nächste Änderung beginnt Mi 16.09.: Mo/Di 12 h → 8 h im
        Wirkungsbereich, Mi–Fr 10 h gehören schon der nächsten Zeile."""
        freeze(monkeypatch)
        self._setup(db, test_user)
        add_row(db, test_user, date(2026, 9, 16), week=block_week(
            mon=self.TWELVE, tue=self.TWELVE, wed=self.TWELVE, thu=self.TWELVE, fri=self.TWELVE))
        impact = _run(db, test_user, test_admin, eff=date(2026, 9, 8), week=block_week(
            mon=self.EIGHT, tue=self.EIGHT, wed=self.TWELVE, thu=self.TWELVE, fri=self.TWELVE))
        assert impact.window.end == date(2026, 9, 15)
        assert impact.arbzg == {
            "days_over_10_credited_before": 2, "days_over_10_credited_after": 0, "days_over_10_presence": 2,
            "weeks_over_48_credited_before": 1, "weeks_over_48_credited_after": 0, "weeks_over_48_presence": 1,
        }


class TestTexts:
    def _impact(self, **overrides):
        base = dict(
            window=None, grace=15, old_schedule=None, new_schedule=None, changed_weekdays=[0], stale_closed=0,
            reclamp=None, open_entry_loses=False, absences=[], credit_reductions=[],
            target_delta=Decimal("0"), credited_delta=Decimal("0"), saldo_delta=Decimal("0"),
            open_day_saldo_delta=Decimal("0"), shortening_reasons=[], shortening_closed_years=[],
            earliest_lossless_date=TODAY, earliest_lossless_note=None, months=[], arbzg={}, entries_before={},
        )
        base.update(overrides)
        return svc.ChangeImpact(**base)

    def _reclamp(self, losing: int):
        from app.services.work_window_service import ReclampChange, ReclampResult
        changes = [ReclampChange(uuid4(), MONDAYS[1], t(15), t(18), 0, Decimal("3"), t(15), t(17, 15), 0,
                                 Decimal("2.25"), None, 15) for _ in range(losing)]
        return ReclampResult(changes, [], [])

    def test_shortening_messages(self):
        a = self._impact(reclamp=self._reclamp(3), shortening_reasons=["entries"])
        assert svc.protection_error(a, None, deleting=False, reset_offered=False) == (
            "Rückwirkende Verkürzung (3 Einträge verlieren angerechnete Zeit): Bitte Grund, Begründung und die "
            "Bestätigung zum Vergütungsrisiko angeben – oder die Änderung ab dem 08.10.2026 wirksam werden lassen.")
        b = self._impact(reclamp=self._reclamp(0), shortening_reasons=["saldo"], saldo_delta=Decimal("-3.75"))
        assert "(Überstundenkonto −3:45 h)" in svc.protection_error(b, None, deleting=False, reset_offered=False)
        o = self._impact(reclamp=self._reclamp(0), shortening_reasons=["saldo"], open_day_saldo_delta=Decimal("-1"))
        assert "(Soll heute +1:00 h während eingestempelt)" in svc.protection_error(
            o, None, deleting=False, reset_offered=False)
        c = self._impact(reclamp=self._reclamp(0), shortening_reasons=["absence_credit"], credit_reductions=[object()])
        assert "(1 Abwesenheits-Gutschrift sinkt)" in svc.protection_error(c, None, deleting=False, reset_offered=False)

    def test_delete_messages_and_p25(self):
        a = self._impact(reclamp=self._reclamp(1), shortening_reasons=["entries"])
        assert svc.protection_error(a, None, deleting=True, reset_offered=True) == (
            "Das Löschen verkürzt rückwirkend (1 Eintrag verliert angerechnete Zeit): Bitte Grund, Begründung und "
            "die Bestätigung zum Vergütungsrisiko angeben – oder ab dem 08.10.2026 auf den vorherigen Stand "
            "zurücksetzen.")
        assert svc.protection_error(a, None, deleting=True, reset_offered=False).endswith("– oder abbrechen.")
        note = svc.P25_NOTE.format(date="01.10.2026")
        n = self._impact(reclamp=self._reclamp(1), shortening_reasons=["entries"], earliest_lossless_date=None,
                         earliest_lossless_note=note)
        assert svc.protection_error(n, None, deleting=False, reset_offered=False).endswith(f"– oder abbrechen: {note}")

    def test_reason_rules(self):
        a = self._impact(reclamp=self._reclamp(1), shortening_reasons=["entries"])
        assert svc.protection_error(a, WorkingHoursChangeDelete(**RETRO_REASON), deleting=False,
                                    reset_offered=False) is None
        other = WorkingHoursChangeDelete(**dict(RETRO_REASON, retroactive_reason_type="sonstiges"))
        assert svc.protection_error(a, other, deleting=False, reset_offered=False) == svc.SONSTIGES_CONFIRM_DETAIL
        no_hook = WorkingHoursChangeDelete(**dict(RETRO_REASON, wage_risk_confirmed=False))
        assert svc.protection_error(a, no_hook, deleting=False, reset_offered=False).startswith("Rückwirkende Verkürzung")
        assert svc.protection_error(self._impact(), None, deleting=False, reset_offered=False) is None

    def test_milog_warnings(self, test_user):
        shortening = self._impact(reclamp=self._reclamp(1), shortening_reasons=["entries"])
        assert svc.milog_warnings(test_user, shortening) == [svc.MILOG_GENERAL_WARNING]
        test_user.agreed_monthly_hours = 43.0
        assert svc.milog_warnings(test_user, shortening) == [svc.MILOG_ACCOUNT_WARNING, svc.MILOG_GENERAL_WARNING]
        assert svc.milog_warnings(test_user, self._impact()) == []


def test_reset_body_for_every_kind_of_predecessor():
    cid = uuid4()

    def sched(**kw):
        base = dict(weekly_hours=Decimal("40"), use_daily_schedule=False, day_hours=(None,) * 5,
                    work_days_per_week=5, blocks=None, block_pauses=None)
        base.update(kw)
        return calculation_service.Schedule(**base)

    assert svc.reset_body(sched(), TODAY, cid) == {
        "effective_from": "2026-10-08", "reset_of_change_id": str(cid), "use_daily_schedule": False,
        "weekly_hours": 40.0, "work_days_per_week": 5, "remove_legacy_window": True}
    from app.services import work_blocks_service as wbs
    new = wbs.parse_week_blocks(ANNA_WEEK)
    assert svc.reset_body(sched(blocks=new.blocks, block_pauses=new.pauses), TODAY, cid) == {
        "effective_from": "2026-10-08", "reset_of_change_id": str(cid), "blocks": ANNA_WEEK}
    legacy = wbs.parse_week_blocks(legacy_week(mon=("07:30", "16:30")))
    body = svc.reset_body(sched(blocks=legacy.blocks, block_pauses=legacy.pauses, use_daily_schedule=True,
                                day_hours=(Decimal("8"), Decimal("8"), None, None, None), work_days_per_week=2),
                          TODAY, cid)
    assert body == {"effective_from": "2026-10-08", "reset_of_change_id": str(cid), "use_daily_schedule": True,
                    "hours_monday": 8.0, "hours_tuesday": 8.0, "hours_wednesday": None, "hours_thursday": None,
                    "hours_friday": None, "work_days_per_week": 2}
