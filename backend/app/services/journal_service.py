"""Monatsjournal-Service: Tagesgenaue Übersicht über Zeit- und Abwesenheitseinträge."""
from datetime import date
from calendar import monthrange
from decimal import Decimal
from typing import Dict, List, Any
from sqlalchemy.orm import Session
from sqlalchemy import extract

from app.models import User, TimeEntry, Absence, PublicHoliday, AbsenceType
from app.services import calculation_service


_ABSENCE_TYPE_MAP = {
    AbsenceType.VACATION: "vacation",
    AbsenceType.SICK: "sick",
    AbsenceType.TRAINING: "training",
    AbsenceType.OVERTIME: "overtime",
    AbsenceType.OTHER: "other",
}


def get_journal(db: Session, user: User, year: int, month: int) -> Dict[str, Any]:
    _, last_day = monthrange(year, month)

    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        extract("year", TimeEntry.date) == year,
        extract("month", TimeEntry.date) == month,
    ).order_by(TimeEntry.date, TimeEntry.start_time).all()

    entries_by_date: Dict[date, List[TimeEntry]] = {}
    for e in entries:
        entries_by_date.setdefault(e.date, []).append(e)

    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        extract("year", Absence.date) == year,
        extract("month", Absence.date) == month,
    ).all()

    absences_by_date: Dict[date, List[Absence]] = {}
    for a in absences:
        absences_by_date.setdefault(a.date, []).append(a)

    holidays = db.query(PublicHoliday).filter(
        extract("year", PublicHoliday.date) == year,
        extract("month", PublicHoliday.date) == month,
    ).all()
    holiday_map: Dict[date, str] = {h.date: h.name for h in holidays}

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
        elif day_absences:
            day_type = _ABSENCE_TYPE_MAP.get(day_absences[0].type, "other")
        elif day_entries:
            day_type = "work"
        else:
            day_type = "empty"

        time_hours = Decimal(str(sum(e.net_hours for e in day_entries)))
        absence_sum = Decimal(str(sum(float(a.hours) for a in day_absences))) if day_absences else Decimal("0")

        if is_weekend or is_holiday_day:
            actual_hours = time_hours
            target_hours = Decimal("0")
        elif day_absences and not day_entries:
            # Pure absence day: show absence hours in Ist column
            actual_hours = absence_sum
            if day_absences[0].type == AbsenceType.TRAINING:
                # Training counts like work – use normal daily target
                weekly_hours = calculation_service.get_weekly_hours_for_date(db, user, d)
                target_hours = calculation_service.get_daily_target_for_date(user, d, weekly_hours)
            else:
                # Sick / vacation / overtime / other: target = absence hours → balance = 0
                target_hours = absence_sum
        else:
            actual_hours = time_hours
            weekly_hours = calculation_service.get_weekly_hours_for_date(db, user, d)
            target_hours = calculation_service.get_daily_target_for_date(user, d, weekly_hours)

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
                    "type": a.type.value,
                    "hours": float(Decimal(str(a.hours)).quantize(Decimal("0.01"))),
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
