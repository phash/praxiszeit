"""Plan 2026-11-21 Task 3: ``run_change`` erkennt gewählte Einträge an.

Kundenfall vom 20.11.2026: erster Arbeitstag 01.10., Basiszeile mit Blöcken an
allen fünf Werktagen, die Änderung ab 01.10. setzt Blöcke nur an Mo + Di. Die
Aushilfe-Einträge an Mi/Do fallen damit auf 0 h (Werktag ohne Block) — außer sie
werden im selben Schritt anerkannt.

Jeder Test ruft ``run_change`` direkt; die Fixture-Session wird je Test verworfen."""
from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models import AbsenceType, TimeEntry, TimeEntryAuditLog
from app.schemas.working_hours_change import TimeEntryChangeOut
from app.services import credit_override_service as cos, reclamp_audit, wh_change_service as svc
from tests.conftest import DEFAULT_TENANT_ID
from tests.wh_change_helpers import absence, add_row, change_row, entry, freeze, t
from tests.work_blocks_fixtures import block_week

TODAY = date(2026, 11, 20)     # Freitag — Tag des Kundenfalls
FIRST = date(2026, 10, 1)      # erster Arbeitstag (Donnerstag)
WED, THU, MON = date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 12)

_BASE_DAY = [("07:55", "13:25"), ("14:55", "17:55")]
BASE_WEEK = block_week(mon=_BASE_DAY, tue=_BASE_DAY, wed=_BASE_DAY, thu=_BASE_DAY, fri=_BASE_DAY)
# Mo + Di mit früherem Beginn: die Hülle beginnt um 07:15 statt 07:40 — der am
# 12.10. von der Basis gekappte Beginn (Stempel 07:35) wird wieder angerechnet.
# So steht der Montag als GEWINN in ``reclamp.changed`` (Neukappung ohne Verlust).
_NEW_DAY = [("07:30", "13:00"), ("14:30", "17:30")]
MON_TUE = block_week(mon=_NEW_DAY, tue=_NEW_DAY)


def _customer_case(db, user, *, base=None):
    """Basiszeile ab 01.10. und drei geschlossene Einträge: Mi 07.10. 07:50–12:05,
    Do 08.10. 07:50–12:35 (beide ungekappt), Mo 12.10. 07:40–12:00 (Stempel ab
    07:35, von der Basis-Hülle 07:40 gekappt)."""
    user.first_work_day = FIRST
    db.commit()
    baseline = add_row(db, user, FIRST, note=reclamp_audit.BASELINE_ROW_NOTE, **(base or {"week": BASE_WEEK}))
    entries = SimpleNamespace(
        wed=entry(db, user, WED, t(7, 50), t(12, 5)),
        thu=entry(db, user, THU, t(7, 50), t(12, 35)),
        mon=entry(db, user, MON, t(7, 40), t(12), raw_start=t(7, 35)),
    )
    return baseline, entries


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    freeze(monkeypatch, TODAY)


def _run(db, user, admin, baseline, *, ids=(), lock=False, week=MON_TUE):
    """Änderung ab 01.10.: die Basiszeile wird an Ort und Stelle ersetzt (wie
    der Router mit ``replace``)."""
    def apply():
        db.delete(baseline)
        db.flush()
        db.add(change_row(user, FIRST, week=week))

    return svc.run_change(db, user, admin_id=admin.id, effective_from=FIRST, apply=apply,
                          recognize_entry_ids=frozenset(ids), lock_recognized=lock)


def _change_on(impact, d):
    [c] = [c for c in impact.reclamp.changed if c.date == d]
    return c


def _net(e) -> Decimal:
    return Decimal(str(e.net_hours))


def _override_rows(db, user) -> list:
    return db.query(TimeEntryAuditLog).filter(
        TimeEntryAuditLog.user_id == user.id,
        TimeEntryAuditLog.tenant_id == DEFAULT_TENANT_ID,
        TimeEntryAuditLog.source == cos.CREDIT_OVERRIDE_SOURCE,
    ).all()


def test_without_selection_is_entries_shortening(db, test_user, test_admin):
    baseline, e = _customer_case(db, test_user)
    impact = _run(db, test_user, test_admin, baseline)
    assert svc.SHORTENING_ENTRIES in impact.shortening_reasons
    wed = _change_on(impact, WED)
    assert wed.new_net == 0
    assert impact.entry_flags[wed.entry_id]["blockless_workday"] is True
    mon = _change_on(impact, MON)
    assert mon.new_net > mon.old_net
    assert impact.entry_flags[mon.entry_id]["blockless_workday"] is False
    assert impact.recognized_ids == frozenset()
    assert impact.logged_changes == impact.reclamp.changed
    assert _override_rows(db, test_user) == []


def test_selection_removes_shortening(db, test_user, test_admin):
    baseline, e = _customer_case(db, test_user)
    impact = _run(db, test_user, test_admin, baseline, ids={e.wed.id, e.thu.id})
    assert svc.SHORTENING_ENTRIES not in impact.shortening_reasons
    db.flush()
    for x in (e.wed, e.thu):
        db.refresh(x)
        assert x.credit_override is True
        assert (x.raw_start_time, x.raw_end_time, x.uncredited_minutes) == (None, None, 0)
    assert (_net(e.wed), _net(e.thu)) == (Decimal("4.25"), Decimal("4.75"))
    assert {str(i) for i in impact.recognized_ids} == {str(e.wed.id), str(e.thu.id)}
    assert [c.date for c in impact.logged_changes] == [MON]
    # Die Liste der Kandidaten bleibt vollständig (stabil beim Setzen der Häkchen).
    assert sorted(c.date for c in impact.reclamp.changed) == [WED, THU, MON]
    # Protokoll fürs Anerkennen: Vorher = Stand VOR der Änderung (Task 2).
    rows = {r.time_entry_id: r for r in _override_rows(db, test_user)}
    assert (rows[e.wed.id].old_start_time, rows[e.wed.id].old_end_time) == (t(7, 50), t(12, 5))
    assert (rows[e.thu.id].old_start_time, rows[e.thu.id].old_end_time) == (t(7, 50), t(12, 35))
    assert len(rows) == 2


def test_selection_with_row_locks(db, test_user, test_admin):
    """Speicherpfad (``lock_recognized``): dieselbe Wirkung über ``load_entry_locked``."""
    baseline, e = _customer_case(db, test_user)
    impact = _run(db, test_user, test_admin, baseline, ids={e.wed.id}, lock=True)
    db.refresh(e.wed)
    assert e.wed.credit_override is True
    assert {str(i) for i in impact.recognized_ids} == {str(e.wed.id)}


def test_recognize_id_outside_change_rejected(db, test_user, test_admin):
    baseline, e = _customer_case(db, test_user)
    september = entry(db, test_user, date(2026, 9, 15), t(8), t(12))
    with pytest.raises(HTTPException) as exc:
        _run(db, test_user, test_admin, baseline, ids={e.wed.id, september.id})
    assert exc.value.status_code == 400
    assert exc.value.detail == svc.NOT_AFFECTED_DETAIL.format(date="15.09.2026")
    assert "15.09.2026" in exc.value.detail


def test_unknown_recognize_id_is_404(db, test_user, test_admin):
    """Der Router weist fremde/unbekannte IDs vorher ab (Task 4); der Dienst
    selbst behauptet nie „nicht betroffen" für einen Eintrag, den es nicht gibt."""
    import uuid

    baseline, e = _customer_case(db, test_user)
    with pytest.raises(HTTPException) as exc:
        _run(db, test_user, test_admin, baseline, ids={uuid.uuid4()})
    assert exc.value.status_code == 404


def test_auto_closed_selection_rejected(db, test_user, test_admin):
    baseline, e = _customer_case(db, test_user)
    auto = entry(db, test_user, date(2026, 10, 14), t(7, 50), t(18, 10), raw_end=time(23, 59),
                 auto_closed=True)
    with pytest.raises(HTTPException) as exc:
        _run(db, test_user, test_admin, baseline, ids={auto.id})
    assert exc.value.status_code == 400
    assert exc.value.detail == cos.AUTO_CLOSED_DETAIL


def test_auto_closed_entry_is_not_recognizable(db, test_user, test_admin):
    baseline, e = _customer_case(db, test_user)
    auto = entry(db, test_user, date(2026, 10, 14), t(7, 50), t(18, 10), raw_end=time(23, 59),
                 auto_closed=True)
    impact = _run(db, test_user, test_admin, baseline)
    assert impact.entry_flags[auto.id]["recognizable"] is False
    assert impact.entry_flags[e.wed.id]["recognizable"] is True


def test_newly_clamped_flag(db, test_user, test_admin):
    """Basis im Stundenmodell (ohne Blöcke): die neuen Blöcke kappen zum ersten Mal."""
    baseline, e = _customer_case(db, test_user, base={"weekly_hours": 40})
    mon19 = entry(db, test_user, date(2026, 10, 19), t(7), t(12))
    impact = _run(db, test_user, test_admin, baseline)
    assert _change_on(impact, date(2026, 10, 19)).new_start == t(7, 15)
    assert impact.entry_flags[mon19.id]["newly_clamped"] is True
    assert impact.entry_flags[e.wed.id]["newly_clamped"] is True


def test_not_newly_clamped_with_block_baseline(db, test_user, test_admin):
    baseline, e = _customer_case(db, test_user)
    impact = _run(db, test_user, test_admin, baseline)
    assert impact.entry_flags[e.mon.id]["newly_clamped"] is False
    assert impact.entry_flags[e.wed.id]["newly_clamped"] is False


class TestOldDayUnclamped:
    D = date(2026, 10, 7)   # Mittwoch

    @staticmethod
    def _sched(blocks, pauses=None):
        return SimpleNamespace(blocks=blocks, block_pauses=pauses)

    def test_no_block_model(self):
        assert svc._old_day_unclamped(self._sched(None), {}, self.D) is True

    def test_hours_off_before(self):
        sched = self._sched(([], [], [(480, 720)], [], []), (0, 0, 0, 0, 0))
        assert svc._old_day_unclamped(sched, {self.D: False}, self.D) is True

    def test_legacy_day_without_window(self):
        sched = self._sched(([(480, 720)], [], [], [], []), (None, None, None, None, None))
        assert svc._old_day_unclamped(sched, {self.D: True}, self.D) is True

    def test_day_with_blocks(self):
        sched = self._sched(([], [], [(480, 720)], [], []), (0, 0, 0, 0, 0))
        assert svc._old_day_unclamped(sched, {self.D: True}, self.D) is False

    def test_blockless_day_in_block_model_was_clamped(self):
        sched = self._sched(([(480, 720)], [], [], [], []), (0, 0, 0, 0, 0))
        assert svc._old_day_unclamped(sched, {}, self.D) is False


def test_preview_fields_flags(db, test_user, test_admin):
    baseline, e = _customer_case(db, test_user)
    impact = _run(db, test_user, test_admin, baseline, ids={e.wed.id})
    fields = svc.preview_fields(impact)
    rows = {r["date"]: r for r in fields["time_entry_changes"]}
    assert set(rows) == {WED, THU, MON}
    assert (rows[WED]["recognized"], rows[WED]["recognizable"], rows[WED]["blockless_workday"]) == (
        True, True, True)
    assert rows[WED]["newly_clamped"] is False
    assert (rows[THU]["recognized"], rows[THU]["recognizable"], rows[THU]["blockless_workday"]) == (
        False, True, True)
    assert (rows[MON]["recognized"], rows[MON]["blockless_workday"]) == (False, False)
    # Zahlen über die protokollierten Änderungen (ohne Anerkannte).
    assert fields["affected_time_entries"] == 2
    assert fields["lost_credited_hours"] == pytest.approx(4.75)
    for row in fields["time_entry_changes"]:
        TimeEntryChangeOut(**row)



def test_preview_rows_report_the_raw_stamp(db, test_user, test_admin):
    """Folgeauftrag zu Task 6: „gestempelt" in der Liste zeigt den Rohstempel VOR
    der Änderung, nicht die schon gekappte Zeit. Der Montag war vor der Änderung
    am Beginn gekappt (Stempel 07:35, angerechnet ab 07:40)."""
    baseline, e = _customer_case(db, test_user)
    impact = _run(db, test_user, test_admin, baseline)
    rows = {r["date"]: r for r in svc.preview_fields(impact)["time_entry_changes"]}
    mon = rows[MON]
    assert (mon["old_start"], mon["old_end"]) == (t(7, 40), t(12))
    assert (mon["raw_start"], mon["raw_end"]) == (t(7, 35), t(12))
    # Ungekappt vor der Änderung: Rohstempel = angerechnete Zeit.
    assert (rows[WED]["raw_start"], rows[WED]["raw_end"]) == (t(7, 50), t(12, 5))
    out = TimeEntryChangeOut(**mon)
    assert (out.raw_start, out.raw_end) == (t(7, 35), t(12))


class TestMixedDay:
    """Misch-Tag (Abwesenheit + Eintrag, gebucht mit ``keep_time_entries``):
    Anerkennen im Dialog == Speichern und danach einzeln anerkennen — dieselbe
    Gutschrift, genau EINE ``credit_override``-Zeile (die des Eintrags), und die
    Abwesenheit steht in ``impact.absences`` (der Router protokolliert sie wie
    jede Rückrechnung)."""

    def _compare(self, db, user, admin, baseline, e_id, absence_id):
        impact = _run(db, user, admin, baseline, ids={e_id})
        db.flush()
        hours_dialog = _absence_hours(db, absence_id)
        overrides = [r.time_entry_id for r in _override_rows(db, user)]
        in_absences = any(str(a.absence_id) == str(absence_id) for a in impact.absences)
        db.rollback()

        entry_rows = db.query(TimeEntry).filter(TimeEntry.id == e_id).all()
        assert entry_rows and entry_rows[0].credit_override is False
        baseline_again = _baseline(db, user)
        _run(db, user, admin, baseline_again)
        [single] = db.query(TimeEntry).filter(TimeEntry.id == e_id).all()
        assert cos.apply_credit_override(db, single, changed_by_id=admin.id, on_request=False)
        db.flush()
        hours_single = _absence_hours(db, absence_id)
        return hours_dialog, hours_single, overrides, in_absences

    def test_recognize_on_mixed_day_f1_matches_single(self, db, test_user, test_admin):
        baseline, e = _customer_case(db, test_user)
        # Krank am 07.10. neben dem Eintrag: beim Buchen auf 8,5 − 4,25 h geklemmt.
        sick = absence(db, test_user, WED, AbsenceType.SICK, 4.25)
        dialog, single, overrides, in_absences = self._compare(
            db, test_user, test_admin, baseline, e.wed.id, sick.id)
        assert dialog == single
        assert overrides == [e.wed.id]
        assert in_absences

    def test_recognize_on_mixed_monday_f1_matches_single(self, db, test_user, test_admin):
        """Tag MIT Soll nach der Änderung: hier wirkt die F1-Klemmung wirklich
        (Gutschrift = Tagessoll − anerkannte Arbeit)."""
        baseline, e = _customer_case(db, test_user)
        d = date(2026, 10, 19)
        mon19 = entry(db, test_user, d, t(7, 40), t(12), raw_start=t(7))
        sick = absence(db, test_user, d, AbsenceType.SICK, 4.17)   # 8,5 − 4,33 beim Buchen
        dialog, single, overrides, in_absences = self._compare(
            db, test_user, test_admin, baseline, mon19.id, sick.id)
        assert dialog == single == Decimal("3.50")              # 8,5 − 5,0 (07:00–12:00)
        assert overrides == [mon19.id]
        assert in_absences

    def test_all_recognised_on_mixed_monday_is_no_shortening(self, db, test_user, test_admin):
        """Branch-Review: alle Einträge anerkannt, darunter der am Misch-Tag mit
        Soll — die F1-Klemmung senkt die Krank-Gutschrift (4,17 → 3,50 h) nur um
        das, was die Arbeit durchs Anerkennen gewinnt (4,33 → 5,0 h). Der Tag
        verliert nichts: keine Verkürzung, kein Schutzpaket (Spec 6.1/6.2)."""
        baseline, e = _customer_case(db, test_user)
        d = date(2026, 10, 19)
        mon19 = entry(db, test_user, d, t(7, 40), t(12), raw_start=t(7))
        sick = absence(db, test_user, d, AbsenceType.SICK, 4.17)
        impact = _run(db, test_user, test_admin, baseline, ids={e.wed.id, e.thu.id, mon19.id})
        assert [(a.date, a.old_hours, a.new_hours, a.f1_clamped, a.credit_reduction) for a in impact.absences] == [
            (d, Decimal("4.17"), Decimal("3.50"), True, False)]
        assert (impact.shortening_reasons, impact.credit_reductions) == ([], [])
        assert impact.earliest_lossless_date is None
        assert svc.protection_error(impact, None, deleting=False, reset_offered=False) is None
        assert _absence_hours(db, sick.id) == Decimal("3.50")

    def test_unrecognised_gain_on_mixed_day_stays_criterion_c(self, db, test_user, test_admin):
        """Kontrolle: ohne Anerkennen am Misch-Tag bleibt (c) wie im Bestand — die
        Neukappung allein hebt die Arbeit (4,33 → 4,75 h), die Gutschrift sinkt
        (``test_entry_gaining_on_a_mixed_day``)."""
        baseline, e = _customer_case(db, test_user)
        d = date(2026, 10, 19)
        entry(db, test_user, d, t(7, 40), t(12), raw_start=t(7))
        absence(db, test_user, d, AbsenceType.SICK, 4.17)
        impact = _run(db, test_user, test_admin, baseline, ids={e.wed.id, e.thu.id})
        assert impact.shortening_reasons == [svc.SHORTENING_ABSENCE_CREDIT]
        assert [(a.date, a.new_hours) for a in impact.credit_reductions] == [(d, Decimal("3.75"))]


def _absence_hours(db, absence_id) -> Decimal:
    from app.models import Absence

    a = db.query(Absence).filter(Absence.id == absence_id).one()
    db.refresh(a)
    return Decimal(str(a.hours))


def _baseline(db, user):
    from app.models import WorkingHoursChange

    return db.query(WorkingHoursChange).filter(
        WorkingHoursChange.user_id == user.id,
        WorkingHoursChange.tenant_id == DEFAULT_TENANT_ID,
        WorkingHoursChange.effective_from == FIRST,
    ).one()
