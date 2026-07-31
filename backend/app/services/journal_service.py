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
        schedule = calculation_service.get_schedule_for_date(db, user, d)
        dt = calculation_service.get_daily_target_for_date(user, d, schedule)
        factor = special_days_service.special_day_target_factor(d, special_day_config)
        if factor is not None:
            dt = dt * factor
        return dt

    def _absence_day_target(d: date, day_absences: List[Absence], worked: Decimal) -> Decimal:
        """L2 + L3 (Audit 2026-07-31): Tages-Soll an einem Tag MIT Abwesenheit —
        aus DERSELBEN Quelle wie die Berechnung (``get_monthly_target``) und die
        §16-Datei (``export_service.absence_day_target``):
        ``calculation_service._day_soll_contribution``.

        Vorher standen hier zwei Einzelpflaster nebeneinander, die beide von der
        maßgeblichen Rechnung abwichen:

        * **L2** (Regression 1.18.0): die Klemmung des soll-reduzierenden Anteils
          auf ``max(0, Tagessoll − gearbeitet)`` wurde auch auf HALBTAGE
          angewandt. ``_day_soll_contribution`` klemmt bewusst nur ganztägige
          Abwesenheiten (``half is False``); ein Halbtag behält immer
          0,5 × Tagessoll. Bei einem Halbtag mit mehr Arbeit als der nicht freien
          Hälfte zeigte die Tageszeile 6/6/0, während die Berechnung im SELBEN
          Response 4/6/+2 sagte (und die §16-Datei ebenfalls 4/6).
        * **L3**: bei einer Abwesenheit OHNE Zeiteintrag wurde
          ``actual = target = Σ absence.hours`` gesetzt. Bei einem Halbtag schrieb
          das die offene Arbeitshälfte als ERBRACHTES Ist gut (4/4/0 statt
          4/0/−4) und färbte ausgerechnet die Zeile grün, in der eine fehlende
          Erfassung auffallen soll.

        Ist-Seite: ``gearbeitete Stunden + gutgeschriebene TRAINING/SICK-Stunden``
        — dieselbe Regel wie ``get_range_actual``. TRAINING/SICK/OVERTIME sind
        nicht soll-reduzierend und fallen daher aus der Half-Map heraus (wie im
        Export-Zwilling; im calculation_service erledigt das die Query).

        Ganztagsfälle bleiben byte-identisch: ohne Zeiteintrag 0 (der Tag fällt
        auch aus ``get_monthly_target``), mit behaltenem Zeiteintrag
        ``min(Tagessoll, gearbeitet)`` — genau die 1.18.0-F1-Klemmung.
        """
        soll_reducing = [
            a for a in day_absences
            if a.type not in (AbsenceType.TRAINING, AbsenceType.SICK, AbsenceType.OVERTIME)
        ]
        half_map = calculation_service._soll_reducing_absence_half_map(soll_reducing)
        return calculation_service._day_soll_contribution(
            db, user, d,
            # Feiertage sind oben schon in einen eigenen Zweig abgebogen.
            holiday_dates=set(),
            absence_half_map=half_map,
            wh_changes=None,
            special_cfg=special_day_config,
            worked_map={d: worked},
        )

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

        # Credited absence hours (TRAINING, SICK count as worked)
        credited_sum = Decimal(str(sum(
            float(a.hours) for a in day_absences
            if a.type in (AbsenceType.TRAINING, AbsenceType.SICK)
        )))

        if is_weekend or is_holiday_day:
            # Audit 2026-07-31 (uebernommen aus Welle B): auch hier zaehlen die
            # ist-gutgeschriebenen Stunden (TRAINING/SICK) mit — ``get_range_actual``
            # summiert seine ``credited_absences`` OHNE Feiertags-/Wochenend-
            # Ausnahme. Ohne diesen Summanden widersprach die Tageszeile dem
            # monthly_summary im SELBEN Response, sobald an einem Feiertag eine
            # Krank- oder Fortbildungs-Abwesenheit lag (Feiertag + Krankmeldung
            # ueber mehrere Tage ist der Regelfall). ``credited_sum`` ist 0, wenn
            # kein solcher Eintrag existiert → alle uebrigen Wochenend-/
            # Feiertagszeilen bleiben unveraendert. Das Soll bleibt 0 (Feiertage
            # fallen auch aus ``get_range_target``).
            actual_hours = time_hours + credited_sum
            target_hours = Decimal("0")
        elif day_absences:
            # L2 + L3 (Audit 2026-07-31): EINE Quelle fuer Soll und Ist der
            # Abwesenheits-Tageszeile — identisch zu get_monthly_target/
            # get_monthly_actual und zum §16-Dateiexport. Deckt den frueheren
            # "nur Abwesenheit"- und den "Misch-Tag"-Zweig gemeinsam ab:
            # TRAINING/SICK werden ueber credited_sum dem Ist gutgeschrieben
            # (bei reiner Abwesenheit ist time_hours 0, das Ergebnis also
            # unveraendert deren Stundensumme), OVERTIME zaehlt 0 Ist und laesst
            # das Soll stehen.
            actual_hours = time_hours + credited_sum
            target_hours = _absence_day_target(d, day_absences, time_hours)
        else:
            actual_hours = time_hours
            target_hours = _eff_daily_target(d)

        # #198: Tage ausserhalb des Beschaeftigungsfensters (vor first_work_day /
        # nach last_work_day) zaehlen kein Ist — symmetrisch zu get_monthly_actual
        # (#195; das Tagessoll ist via _eff_daily_target schon 0). Sonst weicht die
        # Summe der Tageszeilen vom angezeigten Monats-Ist ab, sobald ein TimeEntry/
        # SICK ausserhalb des Fensters liegt (Rehire/Import/Datumskorrektur). Die
        # Roh-Eintraege bleiben sichtbar (§16), zaehlen aber 0. target_hours wird
        # ebenfalls genullt (der Helper selbst kennt das Fenster nicht — er
        # bekaeme fuer einen out-of-window Misch-Tag min(Tagessoll, gearbeitet)
        # und erzeugte damit einen phantom-positiven Tages-Saldo neben dem auf 0
        # gesetzten Ist; Review 2026-06-23).
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
