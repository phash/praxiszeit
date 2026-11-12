"""Greedy Auto-Generierung von Schicht-Zuweisungen (#305 M2).

Füllt die (wochentagsbasierten) Slots eines Plans mit Mitarbeitenden, **lesend**
gegenüber dem Berechnungs-/ArbZG-Modell (Abwesenheiten, Wochenstunden,
Überstundenkonto) — schreibt ausschließlich ``shift_assignments``. Erzeugt einen
Entwurf, den der Admin reviewt; aktiviert den Plan NICHT.

Harte Constraints je Slot (Wochentag → konkretes Datum der Zielwoche):
  * Mitarbeiter:in ist für den Arbeitsplatz **eingewiesen** (Skill-Matrix),
  * an dem Datum **nicht ganztägig abwesend**,
  * innerhalb des **Beschäftigungsfensters**,
  * nicht **doppelt** auf zeitlich überlappende Slots desselben Wochentags —
    auch nicht gegenüber Einteilungen in anderen Plänen, die am Zieltag aktiv sind,
  * zeitlich begrenzte Abwesenheiten (Beginn/Ende gesetzt) blockieren nur die
    überlappenden Slots; halbe Tage ohne Uhrzeit blockieren nicht.
Slots an gesetzlichen Feiertagen und ``free``-Sondertagen der Zielwoche werden
übersprungen (``skipped_slot_ids``) — weder besetzt noch als unbesetzt gemeldet.
Zielbesetzung je Slot = ``max(1, min_staff)``.

Weiche Reihenfolge (welche zuerst): wenigste in diesem Lauf zugeteilte Minuten →
geringere Auslastung (Minuten ÷ Wochenstunden) → niedrigeres Überstundenkonto →
stabiler Tie-Break per ``user_id``.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from app.models import User
from app.models.shift_planning import ShiftPlan
from app.models.absence import Absence
from app.models.shift_planning import ShiftSlot, ShiftAssignment, WorkstationQualification
from app.services import calculation_service
from app.services import holiday_service, shift_planning_service, special_days_service


def _minutes(t) -> int:
    return t.hour * 60 + t.minute


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def generate_plan(db: Session, tenant_id, plan, target_monday: date, mode: str = "replace") -> dict:
    """Greedy-fill the plan's slots. Returns ``{assigned, unfilled_slot_ids}``."""
    slots = (
        db.query(ShiftSlot)
        .filter(ShiftSlot.tenant_id == tenant_id, ShiftSlot.shift_plan_id == plan.id)
        .all()
    )
    # #371: ignore slots on weekdays the tenant switched off — they are off the
    # planning surface (not assigned, not reported as unfilled).
    enabled_weekdays = set(shift_planning_service.get_planning_weekdays(db, tenant_id))
    slots = [s for s in slots if s.weekday in enabled_weekdays]
    if not slots:
        return {"assigned": 0, "unfilled_slot_ids": [], "skipped_slot_ids": []}

    # ui-07: Feiertage und free-Sondertage der Zielwoche — dort wird nicht geplant.
    week_start, week_end = target_monday, target_monday + timedelta(days=6)
    closed_dates = {
        d for d in (week_start + timedelta(days=i) for i in range(7))
        if holiday_service.is_holiday(db, d, tenant_id=tenant_id)
    } | special_days_service.free_special_days_in_range(db, tenant_id, week_start, week_end)
    skipped = [s for s in slots if (target_monday + timedelta(days=s.weekday)) in closed_dates]
    skipped_ids = {s.id for s in skipped}
    slot_ids = [s.id for s in slots]  # replace löscht auch die Zuweisungen übersprungener Slots nicht
    slot_ids = [i for i in slot_ids if i not in skipped_ids]
    slots = [s for s in slots if s.id not in skipped_ids]
    if not slots:
        return {"assigned": 0, "unfilled_slot_ids": [], "skipped_slot_ids": [str(s.id) for s in skipped]}

    # qualifications: workstation_id -> set(user_id)
    qmap: dict = defaultdict(set)
    for uid, wsid in (
        db.query(WorkstationQualification.user_id, WorkstationQualification.workstation_id)
        .filter(WorkstationQualification.tenant_id == tenant_id)
        .all()
    ):
        qmap[wsid].add(uid)

    users = (
        db.query(User)
        .filter(User.tenant_id == tenant_id, User.is_active.is_(True), User.is_hidden.is_(False))
        .all()
    )

    # full-day absences overlapping the target week → absent[user_id] = set(dates)
    absent: dict = defaultdict(set)
    # ui-07: zeitlich begrenzte Abwesenheiten → timed_absent[user_id][date] = [(von, bis)] in Minuten
    timed_absent: dict = defaultdict(lambda: defaultdict(list))
    for ab in (
        db.query(Absence)
        .filter(
            Absence.tenant_id == tenant_id,
            # ganztägig ODER mit Uhrzeit; halbe Tage ohne Uhrzeit blockieren nicht (review finding)
            or_(Absence.start_time.isnot(None), Absence.half_day.isnot(True)),
            Absence.date <= week_end,
            # bound the scan to the target week (review finding): an absence
            # overlaps iff it ends on/after week_start — for single-day rows
            # (end_date NULL) that means date >= week_start.
            or_(
                Absence.end_date >= week_start,
                and_(Absence.end_date.is_(None), Absence.date >= week_start),
            ),
        )
        .all()
    ):
        end = ab.end_date or ab.date
        if end < week_start:
            continue
        d, last = max(ab.date, week_start), min(end, week_end)
        while d <= last:
            if ab.start_time is None:
                absent[ab.user_id].add(d)
            else:
                timed_absent[ab.user_id][d].append(
                    (_minutes(ab.start_time), _minutes(ab.end_time) if ab.end_time else 24 * 60)
                )
            d += timedelta(days=1)

    # ui-08: Überstundenkonto nur bei Bedarf (Kandidaten), je Person einmal, mit dem
    # Saldo-Stichtag (#313) und in einem SAVEPOINT — ein DB-Fehler darf die
    # PostgreSQL-Transaktion nicht vergiften (sonst scheitern DELETE/INSERT danach).
    overtime: dict = {}

    def overtime_of(u) -> Decimal:
        if u.id not in overtime:
            try:
                with db.begin_nested():
                    cutoff = calculation_service.get_soll_cutoff_date(db, u)
                    overtime[u.id] = calculation_service.get_overtime_account(
                        db, u, target_monday.year, target_monday.month, cutoff_date=cutoff
                    )
            except Exception:  # noqa: BLE001 — read-only signal; never fail generation on it
                overtime[u.id] = Decimal(0)
        return overtime[u.id]

    assigned_minutes: dict = defaultdict(int)
    user_busy: dict = defaultdict(list)  # user_id -> [(weekday, start_min, end_min)]
    existing_by_slot: dict = defaultdict(set)

    # ui-07: Einteilungen in ANDEREN, am jeweiligen Zieltag aktiven Plänen belegen die Person.
    other_plans = {
        p.id: p
        for p in db.query(ShiftPlan).filter(ShiftPlan.tenant_id == tenant_id, ShiftPlan.id != plan.id).all()
    }
    if other_plans:
        for o_slot, o_assign in (
            db.query(ShiftSlot, ShiftAssignment)
            .join(ShiftAssignment, ShiftAssignment.shift_slot_id == ShiftSlot.id)
            .filter(
                ShiftSlot.tenant_id == tenant_id,
                ShiftAssignment.tenant_id == tenant_id,
                ShiftSlot.shift_plan_id.in_(list(other_plans.keys())),
            )
            .all()
        ):
            o_date = target_monday + timedelta(days=o_slot.weekday)
            if shift_planning_service.is_plan_active_on(other_plans[o_slot.shift_plan_id], o_date):
                user_busy[o_assign.user_id].append(
                    (o_slot.weekday, _minutes(o_slot.start_time), _minutes(o_slot.end_time))
                )

    if mode == "replace":
        db.query(ShiftAssignment).filter(
            ShiftAssignment.tenant_id == tenant_id,
            ShiftAssignment.shift_slot_id.in_(slot_ids),
        ).delete(synchronize_session=False)
        db.flush()
    else:  # fill_gaps — keep existing, seed state from them
        slot_by_id = {s.id: s for s in slots}
        for a in (
            db.query(ShiftAssignment)
            .filter(ShiftAssignment.tenant_id == tenant_id, ShiftAssignment.shift_slot_id.in_(slot_ids))
            .all()
        ):
            existing_by_slot[a.shift_slot_id].add(a.user_id)
            s = slot_by_id[a.shift_slot_id]
            assigned_minutes[a.user_id] += _minutes(s.end_time) - _minutes(s.start_time)
            user_busy[a.user_id].append((s.weekday, _minutes(s.start_time), _minutes(s.end_time)))

    def weekly_minutes(u) -> float:
        return float(u.weekly_hours) * 60 if u.weekly_hours else 1.0

    assigned_total = 0
    unfilled: list = []
    for s in sorted(slots, key=lambda x: (x.weekday, x.start_time)):
        target = max(1, s.min_staff)
        current = set(existing_by_slot.get(s.id, set()))
        need = target - len(current)
        if need <= 0:
            continue
        s_start, s_end = _minutes(s.start_time), _minutes(s.end_time)
        s_dur = s_end - s_start
        slot_date = target_monday + timedelta(days=s.weekday)

        candidates = []
        for u in users:
            if u.id in current:
                continue
            if u.id not in qmap.get(s.workstation_id, set()):
                continue
            if slot_date in absent.get(u.id, set()):
                continue
            if not calculation_service._within_employment_window(u, slot_date):
                continue
            if any(_overlaps(s_start, s_end, ts, te) for (ts, te) in timed_absent.get(u.id, {}).get(slot_date, [])):
                continue
            if any(wd == s.weekday and _overlaps(s_start, s_end, bs, be) for (wd, bs, be) in user_busy[u.id]):
                continue
            candidates.append(u)

        candidates.sort(key=lambda u: (
            assigned_minutes[u.id],
            assigned_minutes[u.id] / (weekly_minutes(u) or 1),
            overtime_of(u),
            str(u.id),
        ))
        for u in candidates[:need]:
            db.add(ShiftAssignment(tenant_id=tenant_id, shift_slot_id=s.id, user_id=u.id))
            assigned_minutes[u.id] += s_dur
            user_busy[u.id].append((s.weekday, s_start, s_end))
            current.add(u.id)
            assigned_total += 1
        if len(current) < target:
            unfilled.append(str(s.id))

    db.commit()
    return {
        "assigned": assigned_total,
        "unfilled_slot_ids": unfilled,
        "skipped_slot_ids": [str(s.id) for s in skipped],
    }
