"""Monatsjournal-Service: Tagesgenaue Übersicht über Zeit- und Abwesenheitseinträge."""
from datetime import date
from calendar import monthrange
from decimal import Decimal
from typing import Dict, List, Any
from sqlalchemy.orm import Session

from app.models import User, TimeEntry, Absence, PublicHoliday, AbsenceType
from app.services import calculation_service, special_days_service
from app.services.date_filters import date_in_month


_ABSENCE_TYPE_MAP = {
    AbsenceType.VACATION: "vacation",
    AbsenceType.SICK: "sick",
    AbsenceType.TRAINING: "training",
    AbsenceType.OVERTIME: "overtime",
    AbsenceType.OTHER: "other",
    AbsenceType.PAID_LEAVE: "paid_leave",  # Fix: sonst als "other" typisiert
}


def get_journal(
    db: Session, user: User, year: int, month: int, include_health_data: bool = True,
) -> Dict[str, Any]:
    """Tagesgenaues Monatsjournal.

    Fix #6 (Art. 9 DSGVO): ``include_health_data=False`` maskiert SICK-Tage
    (Tagestyp + Absence-Label -> "absent"), ohne die Soll-/Ist-/Saldo-Rechnung
    zu verändern (SICK bleibt als gearbeitet angerechnet, wie in reports.py).
    Default True für Abwärtskompatibilität (Eigenansicht ``/journal/me``); der
    Admin-Endpoint gated explizit + auditiert den Zugriff.
    """
    _, last_day = monthrange(year, month)

    # #312/#376 DSGVO: eigene Abwesenheitsgründe können sensibel sein (z. B.
    # „Kind krank"/„Reha") — jede Absence mit reason_id wird (wie SICK) maskiert,
    # wenn keine Gesundheitsdaten angefordert sind. Bei angeforderten Daten zeigt
    # das Label den eigenen Grund-Namen (Parität zu export_/ods_export_service).
    reason_names: Dict[str, str] = {}
    if include_health_data:
        from app.models import AbsenceReason
        reason_names = {
            str(r.id): r.name for r in db.query(AbsenceReason).filter(
                AbsenceReason.tenant_id == user.tenant_id
            ).all()
        }

    def _is_masked(a: Absence) -> bool:
        return not include_health_data and (a.type == AbsenceType.SICK or a.reason_id is not None)

    def _abs_type_label(a: Absence) -> str:
        if _is_masked(a):
            return "absent"
        if a.reason_id is not None:
            return reason_names.get(str(a.reason_id)) or a.type.value
        return a.type.value

    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.tenant_id == user.tenant_id,  # F-026
        date_in_month(TimeEntry.date, year, month),
    ).order_by(TimeEntry.date, TimeEntry.start_time).all()

    entries_by_date: Dict[date, List[TimeEntry]] = {}
    for e in entries:
        entries_by_date.setdefault(e.date, []).append(e)

    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.tenant_id == user.tenant_id,  # F-026
        date_in_month(Absence.date, year, month),
    ).order_by(Absence.date, Absence.type).all()

    absences_by_date: Dict[date, List[Absence]] = {}
    for a in absences:
        absences_by_date.setdefault(a.date, []).append(a)

    # F-026 + CLAUDE.md PublicHoliday rule: scope holidays to the user's tenant.
    holidays = db.query(PublicHoliday).filter(
        date_in_month(PublicHoliday.date, year, month),
        PublicHoliday.tenant_id == user.tenant_id,
    ).all()
    holiday_map: Dict[date, str] = {h.date: h.name for h in holidays}

    # #146/#193: the per-day target rows MUST apply the same special-day factor
    # (24./31.12.) and employment-window guard as get_monthly_target — otherwise
    # the day rows do not sum to monthly_summary.target_hours (a half-day 24.12.
    # showed the full Tagessoll; days before first_work_day showed full target).
    #
    # Finding 3 (Whole-Branch-Review, #377 Baustein 2b): for a
    # use_fixed_monthly_target user, this deliberately stays a per-day PLANNED
    # attendance figure (get_daily_target_for_date's use_daily_schedule
    # fallback), NOT a decomposition of the flat monthly Soll — a flat
    # agreed_monthly_hours target has no per-day home, and the "flexible
    # remainder" (see design spec §5 Bekannte Grenze) is intentionally not
    # smeared across days. The day rows will therefore NOT sum to
    # monthly_summary.target_hours for a fixed-mode user; that summary block
    # (below, via get_monthly_target/get_overtime_account) stays the
    # authoritative Soll. Do not "fix" the day rows to reconcile — see Finding 1
    # for why the summary, not the days, is the source of truth here.
    special_day_config = special_days_service.get_special_day_config(db, user.tenant_id, year)

    def _eff_daily_target(d: date) -> Decimal:
        if not calculation_service._within_employment_window(user, d):
            return Decimal("0")
        weekly_hours = calculation_service.get_weekly_hours_for_date(db, user, d)
        dt = calculation_service.get_daily_target_for_date(user, d, weekly_hours)
        factor = special_days_service.special_day_target_factor(d, special_day_config)
        if factor is not None:
            dt = dt * factor
        return dt

    days = []
    for day_num in range(1, last_day + 1):
        d = date(year, month, day_num)
        weekday = d.weekday()
        is_weekend = weekday >= 5
        is_holiday_day = d in holiday_map

        day_entries = entries_by_date.get(d, [])
        day_absences = absences_by_date.get(d, [])

        if is_weekend:
            day_type = "weekend"
        elif is_holiday_day:
            day_type = "holiday"
        elif day_entries and day_absences:
            day_type = "mixed"
        elif day_absences:
            # Fix #6 + #312/#376: mask a SICK OR custom-reason day type when health
            # data is not requested. Sonst zeigt das Tages-Farb-/Label die base-type.
            if _is_masked(day_absences[0]):
                day_type = "absent"
            else:
                day_type = _ABSENCE_TYPE_MAP.get(day_absences[0].type, "other")
        elif day_entries:
            day_type = "work"
        else:
            day_type = "empty"

        time_hours = Decimal(str(sum(e.net_hours for e in day_entries)))
        absence_sum = Decimal(str(sum(float(a.hours) for a in day_absences))) if day_absences else Decimal("0")

        # Credited absence hours (TRAINING, SICK count as worked)
        credited_sum = Decimal(str(sum(
            float(a.hours) for a in day_absences
            if a.type in (AbsenceType.TRAINING, AbsenceType.SICK)
        )))

        if is_weekend or is_holiday_day:
            actual_hours = time_hours
            target_hours = Decimal("0")
        elif day_absences and not day_entries:
            daily_target = _eff_daily_target(d)
            if day_absences[0].type == AbsenceType.TRAINING:
                actual_hours = absence_sum
                target_hours = daily_target
            elif day_absences[0].type == AbsenceType.SICK:
                actual_hours = absence_sum
                target_hours = daily_target
            elif day_absences[0].type == AbsenceType.OVERTIME:
                actual_hours = Decimal("0")
                target_hours = daily_target
            else:
                # Vacation / other: balance = 0
                actual_hours = absence_sum
                target_hours = absence_sum
        elif day_entries and day_absences:
            # Mixed day: time entries + absences (e.g. half-day work + half-day sick/training)
            daily_target = _eff_daily_target(d)
            actual_hours = time_hours + credited_sum
            # VACATION/OTHER reduzieren das Soll auf Misch-Tagen. OVERTIME NICHT
            # (Review 2026-06-23): get_monthly_target schliesst OVERTIME explizit
            # von der Soll-Reduktion aus (Soll bleibt, Tag zaehlt als 0h Ist) — die
            # Journal-Tageszeile muss dieselbe Regel nutzen, sonst weicht der
            # Tages-Saldo vom Monats-Summary ab.
            target_reducing_sum = Decimal(str(sum(
                float(a.hours) for a in day_absences
                if a.type not in (AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME)
            )))
            target_hours = daily_target - target_reducing_sum
        else:
            actual_hours = time_hours
            target_hours = _eff_daily_target(d)

        # #198: Tage ausserhalb des Beschaeftigungsfensters (vor first_work_day /
        # nach last_work_day) zaehlen kein Ist — symmetrisch zu get_monthly_actual
        # (#195; das Tagessoll ist via _eff_daily_target schon 0). Sonst weicht die
        # Summe der Tageszeilen vom angezeigten Monats-Ist ab, sobald ein TimeEntry/
        # SICK ausserhalb des Fensters liegt (Rehire/Import/Datumskorrektur). Die
        # Roh-Eintraege bleiben sichtbar (§16), zaehlen aber 0. target_hours wird
        # ebenfalls genullt: auf einem out-of-window MISCH-Tag (Eintrag+Absence)
        # waere target = _eff_daily_target(0) − reducing_sum negativ -> sonst ein
        # phantom-positiver Tages-Saldo (Review 2026-06-23).
        if not calculation_service._within_employment_window(user, d):
            actual_hours = Decimal("0")
            target_hours = Decimal("0")

        balance = actual_hours - target_hours

        days.append({
            "date": d.isoformat(),
            "weekday": d.strftime("%A"),
            "type": day_type,
            "is_holiday": is_holiday_day,
            "holiday_name": holiday_map.get(d),
            "time_entries": [
                {
                    "id": str(e.id),
                    "start_time": e.start_time.strftime("%H:%M") if e.start_time else None,
                    "end_time": e.end_time.strftime("%H:%M") if e.end_time else None,
                    "break_minutes": e.break_minutes,
                    "net_hours": float(Decimal(str(e.net_hours)).quantize(Decimal("0.01"))),
                }
                for e in day_entries
            ],
            "absences": [
                {
                    "id": str(a.id),
                    "type": _abs_type_label(a),  # Fix #6: SICK masked unless requested
                    "hours": float(Decimal(str(a.hours)).quantize(Decimal("0.01"))),
                    "start_time": a.start_time.strftime("%H:%M") if a.start_time else None,
                    "end_time": a.end_time.strftime("%H:%M") if a.end_time else None,
                }
                for a in day_absences
            ],
            "actual_hours": float(actual_hours.quantize(Decimal("0.01"))),
            "target_hours": float(target_hours.quantize(Decimal("0.01"))),
            "balance": float(balance.quantize(Decimal("0.01"))),
        })

    monthly_actual = calculation_service.get_monthly_actual(db, user, year, month)
    monthly_target = calculation_service.get_monthly_target(db, user, year, month)
    monthly_balance = monthly_actual - monthly_target

    yearly_overtime = calculation_service.get_overtime_account(db, user, year, month)

    return {
        "user": {
            "id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
        },
        "year": year,
        "month": month,
        "days": days,
        "monthly_summary": {
            "actual_hours": float(monthly_actual.quantize(Decimal("0.01"))),
            "target_hours": float(monthly_target.quantize(Decimal("0.01"))),
            "balance": float(monthly_balance.quantize(Decimal("0.01"))),
        },
        "yearly_overtime": float(yearly_overtime.quantize(Decimal("0.01"))),
    }
