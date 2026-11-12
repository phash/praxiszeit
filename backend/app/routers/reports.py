import logging
from fastapi import APIRouter, Depends, Query, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.requests import Request
from typing import Annotated, List
from decimal import Decimal
from io import BytesIO
from datetime import date, timedelta
from calendar import monthrange
from urllib.parse import quote
from app.database import get_db
from app.models import User, Absence, AbsenceType, TimeEntry, TimeEntryAuditLog
from app.models.public_holiday import PublicHoliday
from app.middleware.auth import require_admin
from app.schemas.reports import EmployeeMonthlyReport, EmployeeYearlyAbsences, WeeklyHoursChangeInPeriod
from app.services import break_validation_service, calculation_service, export_service, holiday_service, ods_export_service, rest_time_service, work_window_service
from app.services.timezone_service import now_local, today_local
from app.services.arbzg_utils import is_night_work
import calendar
import math
from app.services.date_filters import date_in_year, date_in_month, date_in_range, parse_year_month
from app.core.limiter import limiter
from app.services.settings_service import SHOW_YEAR_END_OVERTIME_ADMIN_DASHBOARD, get_bool_setting

logger = logging.getLogger(__name__)

# A2-6: Ausgeblendete (is_hidden) nur auf ausdrücklichen Wunsch — wie
# „Ausgeblendete anzeigen" in der Benutzerliste. Annotated, damit ein direkter
# Funktionsaufruf (Tests) False bekommt und kein (truthy) Query-Objekt.
IncludeHidden = Annotated[bool, Query(description="Ausgeblendete Mitarbeitende einbeziehen (A2-6)")]

router = APIRouter(prefix="/api/admin/reports", tags=["admin-reports"], dependencies=[Depends(require_admin)])


HIDDEN_COUNT_HEADER = "X-Hidden-With-Data-Count"


def _report_users(db: Session, tenant_id, start: date, end: date, response: Response = None) -> list:
    """calc-13: Personen der Bildschirmberichte — dieselbe Auswahl wie die
    §16-Dateien (``export_service.export_users``): aktive, nicht ausgeblendete
    Mitarbeitende PLUS Ausgeschiedene mit Daten im Zeitraum. Sonst widersprechen
    sich Bildschirm und Datei desselben Zeitraums.

    F-026: ``export_users`` filtert explizit nach Mandant.
    """
    if response is not None:
        # Die Bildschirmberichte liefern Listen; die Zahl der ausgeblendeten
        # Personen mit Daten (wie ``hidden_with_data_count`` der ArbZG-Berichte)
        # reist deshalb im Antwortkopf.
        response.headers[HIDDEN_COUNT_HEADER] = str(
            export_service.hidden_users_with_data_count(db, tenant_id, start, end)
        )
    return export_service.export_users(db, tenant_id, start, end, include_hidden=False)


def _period_absences(db: Session, tenant_id, user, abs_type, start: date, end: date, cutoff=None) -> list:
    """calc-07: EINE Abwesenheitsauswahl für Monats- und Wochenbericht.

    Nur Tage im Beschäftigungsfenster der Person; ``cutoff`` (Saldo-Stichtag
    bei ``soll_basis=bis_heute``) kappt nur, wenn übergeben — Urlaub zählt
    vorgebuchte Tage als verbraucht (kein Cutoff), Krankheit nur bis zum
    Stichtag.
    """
    rows = db.query(Absence).filter(
        Absence.user_id == user.id,
        Absence.tenant_id == tenant_id,  # F-026 belt-and-suspenders
        Absence.type == abs_type,
        date_in_range(Absence.date, start, end),
    ).all()
    rows = [a for a in rows if calculation_service._within_employment_window(user, a.date)]
    if cutoff is not None:
        rows = [a for a in rows if a.date <= cutoff]
    return rows


def _audit_health_export(db: Session, current_user: User, note: str) -> None:
    """calc-08: EINE Stelle für das Art.-9-Exportprotokoll (``health_export``).

    Nur flushen (wie die JSON-Berichte, L-2): der Eintrag wird mit
    ``db.commit()`` NACH erfolgreicher Erzeugung (vor ``db.close()``) festgeschrieben —
    scheitert der Export, bleibt kein „exportiert" ohne Lieferung stehen.
    """
    db.add(TimeEntryAuditLog(
        time_entry_id=None,
        user_id=current_user.id,
        changed_by=current_user.id,
        action="health_export",
        source="dsgvo",
        new_note=note,
        tenant_id=current_user.tenant_id,
    ))
    db.flush()


def _wh_changes_by_user(db: Session, tenant_id, users: list) -> dict:
    """Teil A: EIN Preload der Verlaufszeilen aller Berichtspersonen (F-026) —
    ``track_hours`` des Zeitraums kommt aus dem Snapshot, nicht der User-Zeile."""
    return calculation_service.wh_changes_by_user(db, tenant_id, [u.id for u in users])


@router.get("/monthly", response_model=List[EmployeeMonthlyReport])
def get_monthly_report(
    month: str = Query(..., description="Month in YYYY-MM format"),
    include_health_data: bool = Query(False, description="Krankheitsdaten einschließen (Art. 9 DSGVO)"),
    soll_basis: str = Query(
        "bis_heute",
        description="#313 Soll-Basis: 'bis_heute' (bis zum letzten abgeschlossenen Arbeitstag) oder 'monatsende' (voller Monat)",
    ),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get monthly report for all employees.
    Shows target, actual, balance, overtime, vacation, and sick hours.

    #313: ``soll_basis`` schaltet das Monats-Soll um — ``bis_heute`` (Default)
    zählt nur bis zum letzten abgeschlossenen Arbeitstag (kein Monatsanfangs-
    Minus), ``monatsende`` den vollen Monat. Für abgeschlossene Monate sind beide
    identisch.
    """
    if soll_basis not in ("bis_heute", "monatsende"):
        raise HTTPException(status_code=400, detail="soll_basis muss 'bis_heute' oder 'monatsende' sein")
    try:
        year, month_num = parse_year_month(month)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    if include_health_data:
        logger.info(
            "DSGVO-Datenzugriff: Monatsreport %s-%02d aufgerufen von Admin %s",
            year, month_num, current_user.username
        )
        # F-020: Audit log for sensitive health data read (Art. 9 – sick_hours in response)
        audit = TimeEntryAuditLog(
            time_entry_id=None,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="health_data_read",
            source="dsgvo",
            new_note=f"Monatsreport {year}-{month_num:02d} (inkl. Krankheitsstunden) gelesen von Admin: {current_user.username}",
            tenant_id=current_user.tenant_id,
        )
        db.add(audit)
        # L-2: nur flushen — der Audit-Eintrag wird erst committet, NACHDEM der
        # Report fehlerfrei gebaut ist (sonst bliebe bei einem Fehler beim Bauen ein
        # health_data_read-Audit ohne tatsächlich ausgelieferte Daten stehen).
        db.flush()

    month_start, month_end = date(year, month_num, 1), date(year, month_num, monthrange(year, month_num)[1])
    users = _report_users(db, current_user.tenant_id, month_start, month_end, response)
    wh_by_user = _wh_changes_by_user(db, current_user.tenant_id, users)

    show_year_end_projection = get_bool_setting(db, SHOW_YEAR_END_OVERTIME_ADMIN_DASHBOARD, tenant_id=current_user.tenant_id, default=True, )

    reports = []
    _now = now_local()  # #402: Gate für die Jahresende-Projektion (nur aktueller Monat)

    for user in users:
        # #313: per-user cutoff (each user's last finished workday) unless the
        # report is explicitly run on the full-month ('monatsende') basis.
        cutoff = calculation_service.get_soll_cutoff_date(db, user) if soll_basis == "bis_heute" else None
        # Teil A: Stundenzählung an irgendeinem Tag des Monats (Snapshot).
        tracks = calculation_service.tracks_hours_in_range(
            db, user, date(year, month_num, 1), date(year, month_num, monthrange(year, month_num)[1]),
            wh_by_user.get(user.id, []),
        )
        wh = wh_by_user.get(user.id, [])
        target = calculation_service.get_monthly_target(db, user, year, month_num, up_to_date=cutoff,
                                                        wh_changes=wh)
        actual = calculation_service.get_monthly_actual(db, user, year, month_num, up_to_date=cutoff,
                                                        wh_changes=wh)
        # #150: target/actual sind bereits berechnet — get_monthly_balance würde
        # beide pro User redundant neu laden. Identisch zu dessen (actual-target).quantize.
        balance = (actual - target).quantize(Decimal('0.01'))
        overtime = calculation_service.get_overtime_account(db, user, year, month_num, cutoff_date=cutoff)

        # #402: projizierter Jahresende-Saldo — nur im AKTUELLEN Monat sinnvoll
        # (Projektion „von jetzt bis 31.12."). Boundary = derselbe wie bei overtime:
        # bis_heute→cutoff, monatsende→Monatsende (verhindert Doppelzählung künftiger
        # Freizeitausgleich-Tage im laufenden Monat).
        _future_comp = Decimal('0'); _projected = None
        if show_year_end_projection and year == _now.year and month_num == _now.month and tracks:
            _boundary = cutoff if cutoff is not None else date(year, month_num, calendar.monthrange(year, month_num)[1])
            _future_comp = calculation_service.future_freizeitausgleich_impact(db, user, cutoff_date=_boundary)
            if _future_comp > 0:
                _projected = float(overtime) - float(_future_comp)

        # Get vacation and sick hours for the month (F-033: sargable).
        vacation_absences = _period_absences(
            db, current_user.tenant_id, user, AbsenceType.VACATION, month_start, month_end)
        vacation_hours = sum(float(a.hours) for a in vacation_absences)

        # calc-14: Krankheitsdaten (Art. 9) nur berechnen, wenn sie ausgeliefert werden.
        sick_hours = 0.0
        sick_days = 0.0
        if include_health_data:
            sick_absences = _period_absences(
                db, current_user.tenant_id, user, AbsenceType.SICK, month_start, month_end, cutoff)
            sick_hours = sum(float(a.hours) for a in sick_absences)
            sick_days = float(calculation_service.absence_days(db, user, sick_absences).quantize(Decimal('0.1')))

        # Tagesprinzip (§3 BUrlG, #156/#205): Urlaub TAGEBASIERT zählen — exakt
        # wie get_vacation_account (voller Tag 1,0; half_day 0,5; Legacy h÷Tagessoll-
        # des-Tages; untracked rein tagebasiert). NICHT Σh ÷ Ø-Tagessoll, das driftet
        # bei ungleichmäßigem Tagesplan oder Halbtagen.
        vacation_days = float(calculation_service.absence_days(db, user, vacation_absences).quantize(Decimal('0.1')))

        # Use weekly_hours valid at start of report month, not current value.
        # #415: zusätzlich die Änderungen INNERHALB des Monats mitliefern, sonst
        # zeigt die UI einen Wert, der für den halben Monat nicht galt.
        report_date = date(year, month_num, 1)
        wh_segments = calculation_service.weekly_hours_segments(
            db, user, report_date, date(year, month_num, monthrange(year, month_num)[1])
        )
        hist_weekly = wh_segments[0].weekly_hours if wh_segments else \
            calculation_service.get_weekly_hours_for_date(db, user, report_date)

        reports.append(EmployeeMonthlyReport(
            user_id=str(user.id),
            first_name=user.first_name,
            last_name=user.last_name,
            weekly_hours=float(hist_weekly),
            target_hours=float(target),
            actual_hours=float(actual),
            balance=float(balance),
            overtime_cumulative=float(overtime),
            future_comp_hours=float(_future_comp),
            projected_year_end_overtime=_projected,
            vacation_used_hours=vacation_hours,
            vacation_used_days=vacation_days,
            sick_hours=sick_hours,
            sick_days=sick_days,
            exempt_from_arbzg=bool(user.exempt_from_arbzg),
            track_hours=tracks,
            weekly_hours_changes=[
                # Der Vorgaenger gehoert dazu: nur er sagt, ob sich die
                # Arbeitstage geaendert haben (Abschluss-Review #431, Fund 1).
                WeeklyHoursChangeInPeriod.from_segment(seg, previous=wh_segments[i])
                for i, seg in enumerate(wh_segments[1:])
            ],
        ))

    # L-2: Report erfolgreich gebaut -> jetzt erst den (ggf. oben geflushten)
    # health_data_read-Audit-Eintrag dauerhaft festschreiben.
    if include_health_data:
        db.commit()

    return reports


@router.get("/weekly", response_model=List[EmployeeMonthlyReport])
def get_weekly_report(
    week_start: str = Query(..., description="Beliebiges Datum der Woche (YYYY-MM-DD); wird auf Montag normalisiert"),
    include_health_data: bool = Query(False, description="Krankheitsdaten einschließen (Art. 9 DSGVO)"),
    soll_basis: str = Query(
        "bis_heute",
        description="#313 Soll-Basis: 'bis_heute' (bis letzter abgeschlossener Arbeitstag) oder 'monatsende' (volle Woche)",
    ),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """#329: Wochenreport für alle Mitarbeiter — gleiches Schema wie ``/monthly``,
    aber für eine ISO-Kalenderwoche (Mo–So).

    ``week_start`` wird auf den **Montag** der Woche normalisiert, daher darf die
    Woche eine Monats-/Jahresgrenze überschreiten. ``soll_basis`` wirkt wie bei
    ``/monthly``: ``bis_heute`` (Default) kappt die laufende Woche am letzten
    abgeschlossenen Arbeitstag, ``monatsende`` zählt die volle Woche. Die
    Überstunden-Spalte ist der kumulative laufende Saldo zum Ende der Woche.
    """
    if soll_basis not in ("bis_heute", "monatsende"):
        raise HTTPException(status_code=400, detail="soll_basis muss 'bis_heute' oder 'monatsende' sein")
    try:
        anchor = date.fromisoformat(week_start)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Datumsformat (YYYY-MM-DD erwartet)")

    wk_start = anchor - timedelta(days=anchor.weekday())  # Monday
    wk_end = wk_start + timedelta(days=6)                  # Sunday

    if include_health_data:
        logger.info(
            "DSGVO-Datenzugriff: Wochenreport %s–%s aufgerufen von Admin %s",
            wk_start, wk_end, current_user.username,
        )
        # F-020: Audit log for sensitive health data read (Art. 9 – sick_hours in response)
        audit = TimeEntryAuditLog(
            time_entry_id=None,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="health_data_read",
            source="dsgvo",
            new_note=f"Wochenreport {wk_start}–{wk_end} (inkl. Krankheitsstunden) gelesen von Admin: {current_user.username}",
            tenant_id=current_user.tenant_id,
        )
        db.add(audit)
        # L-2: nur flushen — Commit erst nach erfolgreichem Aufbau (siehe /monthly).
        db.flush()

    users = _report_users(db, current_user.tenant_id, wk_start, wk_end, response)
    wh_by_user = _wh_changes_by_user(db, current_user.tenant_id, users)

    show_year_end_projection = get_bool_setting(db, SHOW_YEAR_END_OVERTIME_ADMIN_DASHBOARD, tenant_id=current_user.tenant_id, default=True, )

    reports = []
    _now = now_local()  # #402: Gate für die Jahresende-Projektion (nur aktuelle Woche)

    for user in users:
        # #313: per-user cutoff (last finished workday) unless run on the full basis.
        cutoff = calculation_service.get_soll_cutoff_date(db, user) if soll_basis == "bis_heute" else None
        # Teil A: Stundenzählung an irgendeinem Tag der Woche (Snapshot).
        tracks = calculation_service.tracks_hours_in_range(
            db, user, wk_start, wk_end, wh_by_user.get(user.id, []))
        # #500: Soll/Ist/Saldo + Konto zum Wochenende aus DER einen Wochenrechnung,
        # die auch die Wochenübersicht des Mitarbeiter-Dashboards nutzt.
        week = calculation_service.get_week_summary(db, user, wk_start, cutoff)
        target, actual, balance = week.target, week.actual, week.balance
        overtime = week.cumulative
        ot_cutoff = week.ot_cutoff

        # #402: projizierter Jahresende-Saldo — nur in der AKTUELLEN Woche sinnvoll.
        # Boundary = ot_cutoff (Wochenende bzw. bis_heute-Cutoff), damit künftige
        # Freizeitausgleich-Tage nicht doppelt zählen.
        _future_comp = Decimal('0'); _projected = None
        if show_year_end_projection and wk_end.year == _now.year and wk_start <= _now.date() <= wk_end and tracks:
            _future_comp = calculation_service.future_freizeitausgleich_impact(db, user, cutoff_date=ot_cutoff)
            if _future_comp > 0:
                _projected = float(overtime) - float(_future_comp)

        # Urlaub/Krank in der Woche — dieselbe Auswahl wie /monthly (calc-07):
        # Urlaub zählt vorgebuchte Tage als verbraucht, Krankheit nur bis zum Cutoff.
        vacation_absences = _period_absences(
            db, current_user.tenant_id, user, AbsenceType.VACATION, wk_start, wk_end)
        vacation_hours = sum(float(a.hours) for a in vacation_absences)

        # calc-14: Krankheitsdaten (Art. 9) nur berechnen, wenn sie ausgeliefert werden.
        sick_hours = 0.0
        sick_days = 0.0
        if include_health_data:
            sick_absences = _period_absences(
                db, current_user.tenant_id, user, AbsenceType.SICK, wk_start, wk_end, cutoff)
            sick_hours = sum(float(a.hours) for a in sick_absences)
            sick_days = float(calculation_service.absence_days(db, user, sick_absences).quantize(Decimal('0.1')))

        # Tagesprinzip (§3 BUrlG, #156/#205): Urlaub tagebasiert zählen.
        vacation_days = float(calculation_service.absence_days(db, user, vacation_absences).quantize(Decimal('0.1')))

        # weekly_hours valid at the week's Monday (mirrors /monthly's report_date).
        # #415: Änderungen innerhalb der Woche werden mitgeliefert.
        wk_segments = calculation_service.weekly_hours_segments(db, user, wk_start, wk_end)
        hist_weekly = wk_segments[0].weekly_hours if wk_segments else \
            calculation_service.get_weekly_hours_for_date(db, user, wk_start)

        reports.append(EmployeeMonthlyReport(
            user_id=str(user.id),
            first_name=user.first_name,
            last_name=user.last_name,
            weekly_hours=float(hist_weekly),
            target_hours=float(target),
            actual_hours=float(actual),
            balance=float(balance),
            overtime_cumulative=float(overtime),
            future_comp_hours=float(_future_comp),
            projected_year_end_overtime=_projected,
            vacation_used_hours=vacation_hours,
            vacation_used_days=vacation_days,
            sick_hours=sick_hours,
            sick_days=sick_days,
            exempt_from_arbzg=bool(user.exempt_from_arbzg),
            track_hours=tracks,
            weekly_hours_changes=[
                # Wie im Monatsbericht: der Vorgaenger entscheidet ueber
                # `work_days_changed`.
                WeeklyHoursChangeInPeriod.from_segment(seg, previous=wk_segments[i])
                for i, seg in enumerate(wk_segments[1:])
            ],
        ))

    if include_health_data:
        db.commit()

    return reports


@router.get("/yearly-absences", response_model=List[EmployeeYearlyAbsences])
def get_yearly_absences(
    year: int = Query(..., ge=2000, le=2100, description="Year (e.g., 2025)"),
    include_health_data: bool = Query(False, description="Krankheitsdaten einschließen (Art. 9 DSGVO)"),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get yearly absence summary for all employees.
    Shows vacation, sick, training, and other days.
    """
    if include_health_data:
        logger.info(
            "DSGVO-Datenzugriff: Jahres-Abwesenheitsübersicht %d aufgerufen von Admin %s",
            year, current_user.username
        )
        # F-020: Audit log for sensitive health data read (Art. 9 – sick_days in response)
        audit = TimeEntryAuditLog(
            time_entry_id=None,
            user_id=current_user.id,
            changed_by=current_user.id,
            action="health_data_read",
            source="dsgvo",
            new_note=f"Jahres-Abwesenheitsübersicht {year} (inkl. Krankheitstage) gelesen von Admin: {current_user.username}",
            tenant_id=current_user.tenant_id,
        )
        db.add(audit)
        # L-2: nur flushen — Commit erst nach erfolgreichem Aufbau der Übersicht
        # (siehe get_monthly_report).
        db.flush()

    users = _report_users(db, current_user.tenant_id, date(year, 1, 1), date(year, 12, 31), response)

    results = []
    _today = today_local()  # #501: Gate der Jahresend-Warnung (Q4 des laufenden Jahres)

    for user in users:
        # F-033 + Sprint 3.4: fetch all absences for this user+year in ONE
        # query, group by type in Python. Previous code issued 5 separate
        # queries per user (one per type).
        all_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.tenant_id == current_user.tenant_id,  # F-026 belt-and-suspenders
            date_in_year(Absence.date, year),
        ).all()
        absences_by_type: dict = {}
        for a in all_absences:
            absences_by_type.setdefault(a.type, []).append(a)

        # Finding 2 (Review 2026-07-14): ALL day columns — including vacation —
        # are TAGEBASIERT (Tagesprinzip §3 BUrlG) via calculation_service.
        # absence_days(), exactly the helper /monthly + /weekly already use.
        # The former naive Σh ÷ Ø-Tagessoll approximation always returned 0.0
        # for track_hours=False employees (Absence.hours is always 0 for them)
        # and drifted for uneven per-weekday schedules (use_daily_schedule).
        vacation_account = calculation_service.get_vacation_account(db, user, year)
        vacation_days = float(vacation_account['used_days'])

        def _days(absence_type) -> float:
            return float(
                calculation_service.absence_days(
                    db, user, absences_by_type.get(absence_type, [])
                ).quantize(Decimal('0.1'))
            )

        sick_days = _days(AbsenceType.SICK)
        training_days = _days(AbsenceType.TRAINING)
        overtime_comp_days = _days(AbsenceType.OVERTIME)
        other_days = _days(AbsenceType.OTHER)
        paid_leave_days = _days(AbsenceType.PAID_LEAVE)

        effective_sick_days = sick_days if include_health_data else 0.0
        total_days = vacation_days + effective_sick_days + training_days + overtime_comp_days + other_days + paid_leave_days

        # Remaining vacation from the same account fetched above (day-based).
        remaining_vacation_days = vacation_account['remaining_days']

        # Calculate overtime for the year (up to today for current year, full year otherwise)
        # #313: YTD-Überstunden bis zum letzten abgeschlossenen Arbeitstag
        ytd = calculation_service.get_ytd_summary(
            db, user, year, cutoff_date=calculation_service.get_soll_cutoff_date(db, user)
        )
        overtime_year = ytd['overtime']

        results.append(EmployeeYearlyAbsences(
            user_id=str(user.id),
            first_name=user.first_name,
            last_name=user.last_name,
            vacation_days=vacation_days,
            remaining_vacation_days=float(remaining_vacation_days),
            sick_days=effective_sick_days,
            training_days=training_days,
            overtime_comp_days=overtime_comp_days,
            other_days=other_days,
            paid_leave_days=paid_leave_days,
            overtime_year=float(overtime_year),
            total_days=total_days,
            # #501: dieselbe Regel wie die Warnung im Mitarbeiter-Dashboard.
            has_year_end_warning=calculation_service.has_year_end_vacation_warning(
                remaining_vacation_days, year, _today
            ),
            # Gesamtreview 1.20 B5: das Verfallsdatum des Banners kommt aus den
            # Daten (individuelle Frist), nicht hart „31.03." im Frontend.
            carryover_deadline=calculation_service.vacation_carryover_deadline(user, year),
        ))

    # L-2: Übersicht erfolgreich gebaut -> health_data_read-Audit festschreiben.
    if include_health_data:
        db.commit()

    return results


@router.get("/export")
@limiter.limit("20/minute")
def export_monthly_report(
    request: Request,
    month: str = Query(..., description="Month in YYYY-MM format"),
    include_health_data: bool = Query(False, description="Include sick/health data (Art. 9 DSGVO – logged in audit trail)"),
    include_hidden: IncludeHidden = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Export monthly report as Excel file.
    Creates one sheet per employee with daily breakdown.
    Sick/health data (Art. 9 DSGVO) is omitted by default; pass include_health_data=true to include it (audit-logged).
    """
    try:
        year, month_num = parse_year_month(month)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    if include_health_data:
        _audit_health_export(db, current_user, f"Gesundheitsdaten (Art. 9 DSGVO) im Monatsreport {year}-{month_num:02d} exportiert – Admin: {current_user.username}")

    # Generate Excel file
    excel_file = export_service.generate_monthly_report(db, year, month_num, include_health_data, tenant_id=current_user.tenant_id, include_hidden=include_hidden)

    # F-053: release the DB connection before streaming. The workbook is
    # already fully materialised in the BytesIO, so holding a connection
    # during the client download is wasted pool capacity. Concurrent admin
    # exports would otherwise starve the default pool_size=5.
    if include_health_data:
        db.commit()  # calc-08: Protokoll erst nach erfolgreicher Erzeugung
    db.close()

    # Create filename
    filename = f"PraxisZeit_Monatsreport_{year}_{month_num:02d}.xlsx"

    # Return as streaming response
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'}
    )


@router.get("/export-yearly")
@limiter.limit("20/minute")
def export_yearly_report(
    request: Request,
    year: int = Query(..., ge=2000, le=2100, description="Year (e.g., 2026)"),
    include_health_data: bool = Query(False, description="Include sick/health data (Art. 9 DSGVO – logged in audit trail)"),
    include_hidden: IncludeHidden = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Export yearly report as Excel file.
    Creates:
    - Overview sheet with all employees
    - Absences overview
    - Detail sheet per employee with monthly breakdown
    Sick/health data (Art. 9 DSGVO) is omitted by default; pass include_health_data=true to include it (audit-logged).
    """
    if include_health_data:
        _audit_health_export(db, current_user, f"Gesundheitsdaten (Art. 9 DSGVO) im Jahresreport {year} exportiert – Admin: {current_user.username}")

    excel_file = export_service.generate_yearly_report(db, year, include_health_data, tenant_id=current_user.tenant_id, include_hidden=include_hidden)
    if include_health_data:
        db.commit()  # calc-08: Protokoll erst nach erfolgreicher Erzeugung
    db.close()  # F-053: release pool connection before streaming
    filename = f"PraxisZeit_Jahresreport_{year}.xlsx"
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'}
    )


@router.get("/export-yearly-classic")
@limiter.limit("20/minute")
def export_yearly_report_classic(
    request: Request,
    year: int = Query(..., ge=2000, le=2100, description="Year (e.g., 2026)"),
    include_health_data: bool = Query(False, description="Include sick/health data (Art. 9 DSGVO – logged in audit trail)"),
    include_hidden: IncludeHidden = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Export yearly report in classic format (compact, months as columns).
    Creates one sheet per employee with 12-month overview.
    Sick/health data (Art. 9 DSGVO) is omitted by default; pass include_health_data=true to include it (audit-logged).
    """
    if include_health_data:
        _audit_health_export(db, current_user, f"Gesundheitsdaten (Art. 9 DSGVO) im Jahresreport Classic {year} exportiert – Admin: {current_user.username}")

    excel_file = export_service.generate_yearly_report_classic(db, year, include_health_data, tenant_id=current_user.tenant_id, include_hidden=include_hidden)
    if include_health_data:
        db.commit()  # calc-08: Protokoll erst nach erfolgreicher Erzeugung
    db.close()  # F-053: release pool connection before streaming
    filename = f"PraxisZeit_Jahresreport_Classic_{year}.xlsx"
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'}
    )


ODS_MIME = "application/vnd.oasis.opendocument.spreadsheet"


@router.get("/export-ods")
@limiter.limit("20/minute")
def export_monthly_report_ods(
    request: Request,
    month: str = Query(..., description="Month in YYYY-MM format"),
    include_health_data: bool = Query(False, description="Include sick/health data (Art. 9 DSGVO – logged in audit trail)"),
    include_hidden: IncludeHidden = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Export monthly report as ODS file (Open Document Spreadsheet).
    Sick/health data (Art. 9 DSGVO) is omitted by default; pass include_health_data=true to include it (audit-logged)."""
    try:
        year, month_num = parse_year_month(month)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    if include_health_data:
        _audit_health_export(db, current_user, f"Gesundheitsdaten (Art. 9 DSGVO) im ODS-Monatsreport {year}-{month_num:02d} exportiert – Admin: {current_user.username}")

    ods_file = ods_export_service.generate_monthly_report(db, year, month_num, include_health_data, tenant_id=current_user.tenant_id, include_hidden=include_hidden)
    if include_health_data:
        db.commit()  # calc-08: Protokoll erst nach erfolgreicher Erzeugung
    db.close()  # F-053: release pool connection before streaming
    filename = f"PraxisZeit_Monatsreport_{year}_{month_num:02d}.ods"
    return StreamingResponse(
        ods_file,
        media_type=ODS_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'}
    )


@router.get("/export-pdf")
@limiter.limit("20/minute")
def export_monthly_report_pdf(
    request: Request,
    month: str = Query(..., description="Month in YYYY-MM format"),
    include_health_data: bool = Query(False, description="Include sick/health data (Art. 9 DSGVO – logged in audit trail)"),
    include_hidden: IncludeHidden = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Export monthly report as PDF file (landscape A4, one page per employee)."""
    try:
        year, month_num = parse_year_month(month)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültiges Monatsformat (YYYY-MM erwartet)")

    if include_health_data:
        _audit_health_export(db, current_user, f"Gesundheitsdaten (Art. 9 DSGVO) im PDF-Monatsreport {year}-{month_num:02d} exportiert – Admin: {current_user.username}")

    pdf_file = export_service.generate_monthly_report_pdf(db, year, month_num, include_health_data, tenant_id=current_user.tenant_id, include_hidden=include_hidden)
    if include_health_data:
        db.commit()  # calc-08: Protokoll erst nach erfolgreicher Erzeugung
    db.close()  # F-053: release pool connection before streaming
    filename = f"PraxisZeit_Monatsreport_{year}_{month_num:02d}.pdf"
    return StreamingResponse(
        pdf_file,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'}
    )


@router.get("/export-yearly-ods")
@limiter.limit("20/minute")
def export_yearly_report_ods(
    request: Request,
    year: int = Query(..., ge=2000, le=2100, description="Year (e.g., 2026)"),
    include_health_data: bool = Query(False, description="Include sick/health data (Art. 9 DSGVO – logged in audit trail)"),
    include_hidden: IncludeHidden = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Export yearly detailed report as ODS file.
    Sick/health data (Art. 9 DSGVO) is omitted by default; pass include_health_data=true to include it (audit-logged)."""
    if include_health_data:
        _audit_health_export(db, current_user, f"Gesundheitsdaten (Art. 9 DSGVO) im ODS-Jahresreport {year} exportiert – Admin: {current_user.username}")
    ods_file = ods_export_service.generate_yearly_report(db, year, include_health_data, tenant_id=current_user.tenant_id, include_hidden=include_hidden)
    if include_health_data:
        db.commit()  # calc-08: Protokoll erst nach erfolgreicher Erzeugung
    db.close()  # F-053: release pool connection before streaming
    filename = f"PraxisZeit_Jahresreport_{year}.ods"
    return StreamingResponse(
        ods_file,
        media_type=ODS_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'}
    )


@router.get("/export-yearly-classic-ods")
@limiter.limit("20/minute")
def export_yearly_report_classic_ods(
    request: Request,
    year: int = Query(..., ge=2000, le=2100, description="Year (e.g., 2026)"),
    include_health_data: bool = Query(False, description="Include sick/health data (Art. 9 DSGVO – logged in audit trail)"),
    include_hidden: IncludeHidden = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Export yearly classic report as ODS file.
    Sick/health data (Art. 9 DSGVO) is omitted by default; pass include_health_data=true to include it (audit-logged)."""
    if include_health_data:
        _audit_health_export(db, current_user, f"Gesundheitsdaten (Art. 9 DSGVO) im ODS-Jahresreport Classic {year} exportiert – Admin: {current_user.username}")
    ods_file = ods_export_service.generate_yearly_report_classic(db, year, include_health_data, tenant_id=current_user.tenant_id, include_hidden=include_hidden)
    if include_health_data:
        db.commit()  # calc-08: Protokoll erst nach erfolgreicher Erzeugung
    db.close()  # F-053: release pool connection before streaming
    filename = f"PraxisZeit_Jahresreport_Classic_{year}.ods"
    return StreamingResponse(
        ods_file,
        media_type=ODS_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'}
    )


# ---------------------------------------------------------------------------
# ArbZG-Berichte (§§ 3–6, 11). Personenauswahl für ALLE: _arbzg_users.
# ---------------------------------------------------------------------------

def _arbzg_users(db: Session, tenant_id, start: date, end: date, include_hidden: bool):
    """A2-6 (Audit 2026-11-07): Personen eines ArbZG-Berichts für ``[start, end]``
    und die Zahl der ausgeblendeten Personen mit Daten, die NICHT enthalten sind.

    Dieselbe Auswahl wie die §16-Dateien (``export_service.export_users``):
    aktive Mitarbeitende plus Ausgeschiedene, die im Zeitraum Zeiteinträge oder
    Abwesenheiten haben — vorher fiel eine im November ausgeschiedene Person
    aus der Januar-Auswertung des Vorjahres (§ 11: 15 freie Sonntage) und aus
    dem 24-Wochen-Fenster. Ausgeblendete nur mit ``include_hidden``; ohne den
    Schalter nennt die Antwort ``hidden_with_data_count``, damit niemand still
    fehlt. § 18-befreite Personen nimmt jeder Bericht selbst heraus."""
    users = export_service.export_users(db, tenant_id, start, end, include_hidden=include_hidden)
    hidden = 0 if include_hidden else export_service.hidden_users_with_data_count(db, tenant_id, start, end)
    return users, hidden


def _holiday_dates(db: Session, tenant_id, start: date, end: date) -> set:
    """Feiertage des Mandanten im Zeitraum (F-026), EIN Query je Bericht."""
    return {
        h.date
        for h in db.query(PublicHoliday).filter(
            PublicHoliday.tenant_id == tenant_id,
            PublicHoliday.date >= start,
            PublicHoliday.date <= end,
        ).all()
    }


# Abwesenheiten, die einen Werktag aus dem Durchschnitts-Nenner nehmen (§ 3/§ 6):
# Urlaub, Krankheit, Fortbildung, Sonstiges/unbezahlt, bezahlte Freistellung —
# jede ganztägige Abwesenheit außer dem Freizeitausgleich. Art. 16 lit. b
# RL 2003/88/EG: Urlaubs- und Krankheitszeiten bleiben bei der Berechnung des
# Durchschnitts unberücksichtigt; als 0-h-Werktag verdünnten sie den Schnitt
# (Fix-Runde Audit 2026-11-07: 2 Wochen krank + 10-h-Tage sonst ergaben „konform").
# Fortbildung steht nicht als Zeiteintrag im Zähler — als 0-h-Werktag hätte sie
# denselben Effekt. Der Freizeitausgleich (OVERTIME) bleibt ein Werktag mit 0 h:
# er IST der Ausgleich, den § 3 Satz 2 verlangt.
_NEUTRAL_ABSENCE_TYPES = (
    AbsenceType.VACATION, AbsenceType.SICK, AbsenceType.TRAINING,
    AbsenceType.OTHER, AbsenceType.PAID_LEAVE,
)


def _neutral_absence_dates(db: Session, user, start: date, end: date) -> set:
    return {
        a.date
        for a in db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.tenant_id == user.tenant_id,  # F-026 belt-and-suspenders
            Absence.date >= start,
            Absence.date <= end,
            Absence.type.in_(_NEUTRAL_ABSENCE_TYPES),
        ).all()
    }


def averaging_workdays(user, start: date, end: date, holiday_dates: set, neutral_absence_dates: set) -> int:
    """A1-13 (Audit 2026-11-07): Nenner der Durchschnitte nach § 3 Satz 2 und
    § 6 Abs. 2 ArbZG = WERKTAGE (Mo–Sa) im Zeitraum, ohne Feiertage, ohne Tage
    mit ganztägiger Abwesenheit außer Freizeitausgleich (``_NEUTRAL_ABSENCE_TYPES``:
    Urlaub, Krankheit, Fortbildung, Sonstiges, bezahlte Freistellung) und nur im
    Beschäftigungszeitraum.

    Bis dahin zählte der Nenner nur Mo–Fr mit Soll > 0, während Samstagsarbeit
    im Zähler stand: 45 h in 5 Tagen ergaben Ø 9 h („Verstoß"), gesetzlich sind
    es Ø 7,5 h je Werktag. Das Gesetz rechnet „werktäglich" — unabhängig vom
    Vertrag; deshalb zählt der Samstag auch für Teilzeit- und Mo–Fr-Kräfte."""
    days = 0
    d = start
    while d <= end:
        if (
            d.weekday() < 6
            and d not in holiday_dates
            and d not in neutral_absence_dates
            and calculation_service._within_employment_window(user, d)
        ):
            days += 1
        d += timedelta(days=1)
    return days


@router.get("/rest-time-violations")
def get_rest_time_violations(
    year: int = Query(..., ge=2000, le=2100, description="Year to check"),
    month: int = Query(None, ge=1, le=12, description="Optional month to check"),
    min_rest_hours: float = Query(None, ge=1, le=24, description="Minimum rest hours (default: 11)"),
    include_hidden: IncludeHidden = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get rest time violations for all employees.
    A violation occurs when the time between two work shifts is less than min_rest_hours.
    Default minimum rest time: 11 hours (German law ArbZG §5).
    """
    if month:
        start, end = date(year, month, 1), date(year, month, monthrange(year, month)[1])
    else:
        start, end = date(year, 1, 1), date(year, 12, 31)
    users, hidden = _arbzg_users(db, current_user.tenant_id, start, end, include_hidden)
    violations = rest_time_service.check_all_users_violations(
        db, year, month, min_rest_hours, tenant_id=current_user.tenant_id, users=users,
    )
    return {
        "year": year,
        "month": month,
        "min_rest_hours": rest_time_service.DEFAULT_MIN_REST_HOURS if min_rest_hours is None else min_rest_hours,
        "total_violations": sum(v["violation_count"] for v in violations),
        "employees_affected": len(violations),
        "violations": violations,
        "hidden_with_data_count": hidden,
    }


@router.get("/sunday-summary")
def get_sunday_summary(
    year: int = Query(..., ge=2000, le=2100, description="Year to check (e.g., 2026)"),
    include_hidden: IncludeHidden = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    §11 ArbZG: Get Sunday/holiday work summary per employee for a given year.
    Reports how many Sundays each employee worked and whether the legal minimum
    of 15 free Sundays per year is met.
    """
    import calendar

    # Count total Sundays in the year
    all_sundays = [
        date(year, m, d)
        for m in range(1, 13)
        for d in range(1, calendar.monthrange(year, m)[1] + 1)
        if date(year, m, d).weekday() == 6
    ]
    total_sundays = len(all_sundays)
    min_free_sundays = 15

    users, hidden = _arbzg_users(db, current_user.tenant_id, date(year, 1, 1), date(year, 12, 31), include_hidden)
    result = []

    for user in users:
        if user.exempt_from_arbzg:
            continue  # RPT-12: §18-Leitende konsistent ausnehmen (wie rest-time/24-week)
        # Get all entries on Sundays in this year
        entries = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.tenant_id == user.tenant_id,  # F-026
                TimeEntry.user_id == user.id,
                date_in_year(TimeEntry.date, year),
            )
            .all()
        )
        # calc-05: nur Sonntage im Beschäftigungsfenster der Person zählen
        # (Ein-/Austritt im Jahr); Teiljahr → Pflicht anteilig (aufgerundet).
        window_sundays = {d for d in all_sundays if calculation_service._within_employment_window(user, d)}
        sundays_worked = {
            e.date for e in entries if e.date.weekday() == 6 and e.date in window_sundays
        }
        sundays_worked_count = len(sundays_worked)
        person_total = len(window_sundays)
        free_sundays = person_total - sundays_worked_count
        partial_year = person_total < total_sundays
        person_min_free = (
            math.ceil(min_free_sundays * person_total / total_sundays) if partial_year else min_free_sundays
        )

        result.append({
            "user_id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "sundays_worked": sundays_worked_count,
            "free_sundays": free_sundays,
            "total_sundays_in_year": person_total,
            "partial_year": partial_year,
            "min_free_sundays": person_min_free,
            "compliant": free_sundays >= person_min_free,
        })

    return {
        "year": year,
        "total_sundays_in_year": total_sundays,
        "min_free_sundays": min_free_sundays,
        "employees": result,
        "non_compliant_count": sum(1 for r in result if not r["compliant"]),
        "hidden_with_data_count": hidden,
    }


NIGHT_WORKER_MONTHLY_LIMIT = 8.0  # § 6 Abs. 2 ArbZG: Ø 8 h werktäglich je Kalendermonat


@router.get("/night-work-summary")
def get_night_work_summary(
    year: int = Query(..., ge=2000, le=2100, description="Year to check (e.g., 2026)"),
    include_hidden: IncludeHidden = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    §6 ArbZG: Night work summary per employee for a given year.
    Night hours: 23:00–06:00. Reports how many days each employee
    performed night work and whether they qualify as Nachtarbeitnehmer (>=48 days/year).

    A1-14 (Audit 2026-11-07): für Nachtarbeitnehmer (Kennzeichen gesetzt ODER
    ≥ 48 Nachtarbeitstage) zusätzlich ``monthly`` — je Kalendermonat der
    Durchschnitt je Werktag (§ 6 Abs. 2: Verlängerung auf 10 h nur, wenn im
    Kalendermonat Ø 8 h werktäglich nicht überschritten werden; Nenner wie der
    24-Wochen-Schnitt, ``averaging_workdays``). ``flag_missing`` meldet, dass
    die Person laut Zählung Nachtarbeitnehmer ist, das Kennzeichen am Benutzer
    (das die 8-h-Warnung beim Erfassen auslöst) aber fehlt — gesetzt wird es nur
    von Hand.
    """
    year_start, year_end = date(year, 1, 1), date(year, 12, 31)
    today = today_local()
    # Fix-Runde (VVZ: „JSON-Reportzugriffe werden protokolliert"): die Antwort
    # trägt das gesundheitsnahe Kennzeichen ``is_night_worker`` (und
    # ``flag_missing``) je Person — die Dateien zeigen es nur mit
    # „Krankheitsdaten einschließen" (night_worker_export_value). Der Bericht
    # braucht es für die Monatsauswertung (§ 6 Abs. 2) und die Hinweise; deshalb
    # vermerkt jeder Abruf einen health_data_read wie die anderen Art.-9-Berichte.
    # Nur flushen — Commit erst, wenn der Bericht fehlerfrei gebaut ist (L-2).
    db.add(TimeEntryAuditLog(
        time_entry_id=None,
        user_id=current_user.id,
        changed_by=current_user.id,
        action="health_data_read",
        source="dsgvo",
        new_note=f"Nachtarbeitsbericht {year} (inkl. Kennzeichen Nachtarbeitnehmer) gelesen von Admin: {current_user.username}",
        tenant_id=current_user.tenant_id,
    ))
    db.flush()
    users, hidden = _arbzg_users(db, current_user.tenant_id, year_start, year_end, include_hidden)
    holiday_dates = _holiday_dates(db, current_user.tenant_id, year_start, year_end)
    result = []
    threshold = 48  # §6 ArbZG: Nachtarbeitnehmer if >= 48 days/year

    for user in users:
        if user.exempt_from_arbzg:
            continue  # RPT-12: §18-Leitende konsistent ausnehmen
        entries = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.tenant_id == user.tenant_id,  # F-026
                TimeEntry.user_id == user.id,
                date_in_year(TimeEntry.date, year),
                TimeEntry.end_time.isnot(None),
            )
            .order_by(TimeEntry.date)
            .all()
        )

        night_days = {
            e.date for e in entries if is_night_work(e.start_time, e.end_time)
        }
        night_days_count = len(night_days)

        # Group by month
        by_month: dict = {}
        for d in sorted(night_days):
            m = d.month
            by_month[m] = by_month.get(m, 0) + 1

        is_nachtarbeitnehmer = night_days_count >= threshold
        monthly = []
        if user.is_night_worker or is_nachtarbeitnehmer:
            neutral = _neutral_absence_dates(db, user, year_start, year_end)
            for m in range(1, 13):
                m_start, m_end = date(year, m, 1), date(year, m, monthrange(year, m)[1])
                m_entries = [e for e in entries if m_start <= e.date <= m_end]
                # Fix-Runde: nur Monate mit Arbeit, nie künftige — eine Zeile
                # „0 h ✓ Konform" für Dezember liest sich wie ein Nachweis.
                if not m_entries or m_start > today:
                    continue
                workdays = averaging_workdays(user, m_start, m_end, holiday_dates, neutral)
                credited = sum(float(e.net_hours or 0) for e in m_entries)
                presence = sum(work_window_service.presence_minutes(e) for e in m_entries) / 60.0
                avg = credited / workdays if workdays else 0.0
                presence_avg = presence / workdays if workdays else 0.0
                monthly.append({
                    "month": m,
                    "workdays": workdays,
                    "total_hours": round(credited, 2),
                    "average_daily_hours": round(avg, 2),
                    "presence_hours": round(presence, 2),
                    "presence_average": round(presence_avg, 2),
                    # Arbeit nur an Sonn-/Feiertagen o. Ä. (kein Werktag im
                    # Nenner): kein Urteil statt „konform" mit Ø 0.
                    "compliant": (avg <= NIGHT_WORKER_MONTHLY_LIMIT) if workdays else None,
                })

        result.append({
            "user_id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "night_work_days": night_days_count,
            "is_nachtarbeitnehmer": is_nachtarbeitnehmer,
            "nachtarbeitnehmer_threshold": threshold,
            "by_month": [{"month": m, "days": c} for m, c in sorted(by_month.items())],
            "is_night_worker_flag": bool(user.is_night_worker),
            "flag_missing": is_nachtarbeitnehmer and not user.is_night_worker,
            "monthly": monthly,
            "monthly_violation_count": sum(1 for r in monthly if r["compliant"] is False),
        })

    db.commit()  # L-2: Bericht gebaut -> health_data_read festschreiben
    return {
        "year": year,
        "nachtarbeitnehmer_threshold": threshold,
        "monthly_limit_hours": NIGHT_WORKER_MONTHLY_LIMIT,
        "employees": result,
        "nachtarbeitnehmer_count": sum(1 for r in result if r["is_nachtarbeitnehmer"]),
        "hidden_with_data_count": hidden,
    }


# § 11 Abs. 3 ArbZG: Ersatzruhetag binnen 2 Wochen (Sonntag) bzw. 8 Wochen (Feiertag).
_SUNDAY_WINDOW_DAYS = 14
_HOLIDAY_WINDOW_DAYS = 56
# Abwesenheiten, mit denen ein Ersatzruhetag GEWÄHRT werden kann: das Handbuch
# empfiehlt „Sonstiges"; Freizeitausgleich und bezahlte Freistellung sind
# ebenfalls arbeitsfreie Tage auf Kosten der Arbeitspflicht. Urlaub (eigener
# Anspruch), Krankheit und Fortbildung (Arbeitszeit) gleichen nichts aus.
_REST_DAY_GRANTING_ABSENCES = {AbsenceType.OTHER, AbsenceType.OVERTIME, AbsenceType.PAID_LEAVE}
# „Sonst Arbeitstag laut tatsächlichem Muster": an diesem Wochentag in mindestens
# 2 der 4 Vorwochen gearbeitet (z. B. ohne Stundenzählung, oder jeder 2. Samstag).
_PATTERN_WEEKS = 4
_PATTERN_MIN_WEEKS = 2


def _unsynced_next_year_holidays(db: Session, tenant_id, year: int, range_end: date) -> set:
    """Fix-Runde (Audit 2026-11-07): die Ruhetags-Suche eines Dezember-Einsatzes
    reicht bis zu 8 Wochen ins Folgejahr. Hat der Mandant dessen Feiertage noch
    nicht (``sync_current_and_next_year`` lief noch nicht), galt der 1. Januar
    als freier Werktag und damit als Ersatzruhetag — ein falsches „ausgeglichen".
    Dann rechnet der Bericht die gesetzlichen Feiertage des Bundeslands für das
    Folgejahr selbst (``holiday_service._german_holidays``, ohne zu speichern).
    Sobald für das Folgejahr irgendeine Feiertagszeile existiert, gilt sie."""
    next_year = year + 1
    if range_end.year < next_year:
        return set()
    has_rows = db.query(PublicHoliday.id).filter(
        PublicHoliday.tenant_id == tenant_id,  # F-026
        PublicHoliday.year == next_year,
    ).first() is not None
    if has_rows:
        return set()
    try:
        state = holiday_service.get_holiday_state(db, tenant_id=tenant_id)
        computed = holiday_service._german_holidays(state, next_year)
    except ValueError:
        logger.warning("Feiertage %d für Ersatzruhetag-Bericht nicht berechenbar (Bundesland unbekannt)", next_year)
        return set()
    return {d for d in computed.keys() if date(next_year, 1, 1) <= d <= range_end}


@router.get("/compensatory-rest")
def get_compensatory_rest(
    year: int = Query(..., ge=2000, le=2100, description="Year to check (e.g., 2026)"),
    include_hidden: IncludeHidden = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    §11 ArbZG: Compensatory rest day tracking.
    After Sunday work → 1 free day within 2 weeks.
    After holiday work → 1 free day within 8 weeks.

    A1-01 (Audit 2026-11-07): ein Ersatzruhetag ist ein Tag, an dem die Person
    SONST GEARBEITET HÄTTE und nicht gearbeitet hat (§ 11 Abs. 3 ArbZG). Bis
    dahin zählte jeder Mo–Sa-Tag ohne Eintrag — der ohnehin freie Samstag einer
    Fünf-Tage-Kraft „glich" damit jeden Sonntag aus, auch Feiertage, Urlaubs-
    und künftige Tage; zwei gearbeitete Sonntage ohne einen einzigen Ruhetag
    ergaben „konform". Jetzt zählt ein Tag (Mo–Sa) nur, wenn

    * er laut Vertrags-Snapshot ein Tagessoll > 0 hat (``get_schedule_for_date``)
      ODER die Person an diesem Wochentag in mindestens 2 der 4 Vorwochen
      gearbeitet hat (tatsächliches Muster, z. B. ohne Stundenzählung),
    * er kein Feiertag ist und im Beschäftigungszeitraum liegt,
    * an ihm kein Zeiteintrag steht und keine Abwesenheit außer Sonstiges/
      Freizeitausgleich/bezahlter Freistellung (so wird ein gewährter
      Ersatzruhetag eingetragen; Urlaub, Krankheit, Fortbildung zählen nicht),
    * er vorbei ist (vor heute — die Zukunft weist nichts nach).

    Jeder Ruhetag gleicht genau EINEN Sonn-/Feiertag aus (nicht zwei
    aufeinanderfolgende Sonntage mit demselben Montag): Zuteilung je Ruhetag
    an den offenen Einsatz mit der frühesten Frist (optimal). Einsätze aus den
    letzten 8 Wochen des Vorjahres verbrauchen Ruhetage mit, werden aber nicht
    gemeldet. Läuft die Frist noch (Frist ≥ heute), steht der Einsatz unter
    ``open`` statt unter ``violations``.
    """
    year_start, year_end = date(year, 1, 1), date(year, 12, 31)
    users, hidden = _arbzg_users(db, current_user.tenant_id, year_start, year_end, include_hidden)
    today = today_local()

    # Einsätze ab 8 Wochen vor Jahresbeginn (Verbraucher), Ruhetage bis 8 Wochen
    # nach Jahresende, Muster 4 Wochen davor.
    consumer_start = year_start - timedelta(days=_HOLIDAY_WINDOW_DAYS)
    range_end = year_end + timedelta(days=_HOLIDAY_WINDOW_DAYS)
    data_start = consumer_start - timedelta(weeks=_PATTERN_WEEKS)
    holiday_dates = _holiday_dates(db, current_user.tenant_id, data_start, range_end)
    holiday_dates |= _unsynced_next_year_holidays(db, current_user.tenant_id, year, range_end)
    wh_by_user = calculation_service.wh_changes_by_user(db, current_user.tenant_id, [u.id for u in users])
    result = []

    for user in users:
        if user.exempt_from_arbzg:
            continue  # RPT-12: §18-Leitende konsistent ausnehmen
        wh_changes = wh_by_user.get(user.id, [])
        worked_dates = {
            e.date
            for e in db.query(TimeEntry).filter(
                TimeEntry.tenant_id == user.tenant_id,  # F-026
                TimeEntry.user_id == user.id,
                TimeEntry.date >= data_start,
                TimeEntry.date <= range_end,
            ).all()
        }
        absence_types: dict = {}
        for a in db.query(Absence).filter(
            Absence.tenant_id == user.tenant_id,  # F-026
            Absence.user_id == user.id,
            Absence.date >= consumer_start,
            Absence.date <= range_end,
        ).all():
            absence_types.setdefault(a.date, set()).add(a.type)

        def would_work(d: date) -> bool:
            schedule = calculation_service.get_schedule_for_date(db, user, d, wh_changes=wh_changes)
            if calculation_service.get_daily_target_for_date(user, d, schedule) > 0:
                return True
            weeks = sum(1 for k in range(1, _PATTERN_WEEKS + 1) if d - timedelta(weeks=k) in worked_dates)
            return weeks >= _PATTERN_MIN_WEEKS

        def is_rest_day(d: date) -> bool:
            return (
                d.weekday() <= 5
                and d < today
                and d not in holiday_dates
                and d not in worked_dates
                and calculation_service._within_employment_window(user, d)
                and absence_types.get(d, set()) <= _REST_DAY_GRANTING_ABSENCES
                and would_work(d)
            )

        # Einsätze an Sonn-/Feiertagen (je Datum einmal), mit Frist.
        items = []
        for d in sorted(worked_dates):
            if d < consumer_start or d > year_end:
                continue
            is_sun = d.weekday() == 6
            if not (is_sun or d in holiday_dates):
                continue
            window = _SUNDAY_WINDOW_DAYS if is_sun else _HOLIDAY_WINDOW_DAYS
            items.append({"date": d, "type": "sunday" if is_sun else "holiday",
                          "deadline": d + timedelta(days=window), "window_days": window})

        # Zuteilung: je Ruhetag (chronologisch) an den offenen Einsatz mit der
        # frühesten Frist, dessen Fenster den Tag enthält.
        assigned: dict = {}
        if items:
            d = items[0]["date"] + timedelta(days=1)
            last = max(i["deadline"] for i in items)
            while d <= last:
                pending = [i for i in items if id(i) not in assigned and i["date"] < d <= i["deadline"]]
                if pending and is_rest_day(d):
                    best = min(pending, key=lambda i: (i["deadline"], i["date"]))
                    assigned[id(best)] = d
                d += timedelta(days=1)

        reported = [i for i in items if i["date"] >= year_start]
        violations, open_items, compensated = [], [], []
        for i in reported:
            entry = {"date": i["date"].isoformat(), "type": i["type"], "window_weeks": i["window_days"] // 7,
                     "deadline": i["deadline"].isoformat()}
            if id(i) in assigned:
                compensated.append({**entry, "rest_day": assigned[id(i)].isoformat()})
            elif i["deadline"] >= today:
                open_items.append(entry)
            else:
                violations.append(entry)

        result.append({
            "user_id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "sunday_holiday_days_worked": len(reported),
            "violations": violations,
            "violation_count": len(violations),
            "open": open_items,
            "open_count": len(open_items),
            "compensated": compensated,
            "compliant": len(violations) == 0,
        })

    return {
        "year": year,
        "employees": result,
        "total_violations": sum(r["violation_count"] for r in result),
        "total_open": sum(r["open_count"] for r in result),
        "non_compliant_count": sum(1 for r in result if not r["compliant"]),
        "hidden_with_data_count": hidden,
    }


@router.get("/24-week-average")
def get_24_week_averaging_period(
    end_date: date = Query(None, description="End of the 24-week window (default: today)"),
    include_hidden: IncludeHidden = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    §3 ArbZG: Daily hours may be extended to 10h only if the 8h daily average
    is maintained over 6 calendar months / 24 weeks.

    For each employee, sums all net working hours in the window and compares
    to the allowed budget (8h × Werktage).

    A1-13 (Audit 2026-11-07): ``scheduled_work_days`` (Name aus Kompatibilität)
    sind die WERKTAGE Mo–Sa des Fensters ohne Feiertage, ohne ganztägige
    Abwesenheit außer Freizeitausgleich, nur im Beschäftigungszeitraum
    (``averaging_workdays``). Vorher Mo–Fr mit Soll > 0 (M-ARB2) — der Nenner
    passte nicht zum Zähler (Samstagsarbeit) und nicht zum Gesetz
    („werktäglich"), Teilzeitkräfte mit drei langen Tagen standen fälschlich als
    Verstoß da.

    An employee flagged as non-compliant has systematically exceeded the 10h
    exception allowance and the ArbZG averaging clause no longer covers them.
    """
    if end_date is None:
        # Europe/Berlin, not UTC/container time — consistent with all other
        # business-logic "today" stichtage (Dashboard, YTD, vacation warnings).
        # date.today() rolled the §3 24-week window by a day between 00:00–02:00 CET.
        end_date = today_local()
    start_date = end_date - timedelta(weeks=24)

    users, hidden = _arbzg_users(db, current_user.tenant_id, start_date, end_date, include_hidden)
    result = []

    # Public holidays for the whole window, tenant-scoped (fetched once).
    holiday_dates = _holiday_dates(db, current_user.tenant_id, start_date, end_date)

    for user in users:
        if user.exempt_from_arbzg:
            continue

        entries = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.user_id == user.id,
                TimeEntry.tenant_id == current_user.tenant_id,  # F-026 (E74)
                TimeEntry.date >= start_date,
                TimeEntry.date <= end_date,
                TimeEntry.end_time.isnot(None),
            )
            .all()
        )
        total_hours = sum(float(e.net_hours or 0) for e in entries)
        # Spec 8.1 / P22: zweiter, eigens gekennzeichneter Wert — Anwesenheit laut
        # Stempel (Rohstempel abzüglich erfasster Pausen, bei Auto-Close bis zum
        # wirksamen Ende). Eine Neukappung senkt total_hours, nie diesen Wert.
        presence_hours = sum(work_window_service.presence_minutes(e) for e in entries) / 60.0
        # Spec 8.1/11.1 „je Woche": dieselbe Größe je ISO-Kalenderwoche (Mo–So) —
        # eine Woche > 48 h laut Stempel darf nicht im Fensterdurchschnitt verschwinden.
        # Randwochen zählen nur ihre Tage im Fenster (die Abfrage oben begrenzt).
        presence_by_week: dict[str, int] = {}
        for e in entries:
            iso_year, iso_week, _ = e.date.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
            presence_by_week[key] = presence_by_week.get(key, 0) + work_window_service.presence_minutes(e)
        presence_weeks = [
            {"iso_week": key, "presence_hours": round(minutes / 60.0, 2)}
            for key, minutes in sorted(presence_by_week.items())
        ]

        # A1-13: Werktage (Mo–Sa) ohne Feiertage und ohne ganztägige Abwesenheit
        # außer Freizeitausgleich (_NEUTRAL_ABSENCE_TYPES, Art. 16 lit. b
        # RL 2003/88/EG). #193: nur im Beschäftigungsfenster —
        # Tage vor Eintritt / nach Austritt dürfen den Durchschnitt einer
        # Neueinstellung nicht verdünnen.
        scheduled_days = averaging_workdays(
            user, start_date, end_date, holiday_dates,
            _neutral_absence_dates(db, user, start_date, end_date),
        )

        max_budget = 8.0 * scheduled_days
        average = (total_hours / scheduled_days) if scheduled_days else 0.0
        presence_average = (presence_hours / scheduled_days) if scheduled_days else 0.0

        # Count days where the employee exceeded 8h — these are the days
        # that actually consume the averaging budget.
        over_8h_count = 0
        by_date: dict = {}
        for e in entries:
            by_date.setdefault(e.date, 0.0)
            by_date[e.date] += float(e.net_hours or 0)
        for total in by_date.values():
            if total > 8.0:
                over_8h_count += 1

        result.append({
            "user_id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "window_start": start_date.isoformat(),
            "window_end": end_date.isoformat(),
            "total_hours": round(total_hours, 2),
            "scheduled_work_days": scheduled_days,
            "max_budget_hours": round(max_budget, 2),
            "average_daily_hours": round(average, 2),
            "days_over_8h": over_8h_count,
            "compliant": average <= 8.0,
            "presence_hours": round(presence_hours, 2),
            "presence_average": round(presence_average, 2),
            "presence_weeks": presence_weeks,
        })

    return {
        "window_start": start_date.isoformat(),
        "window_end": end_date.isoformat(),
        "employees": result,
        "non_compliant_count": sum(1 for r in result if not r["compliant"]),
        "hidden_with_data_count": hidden,
    }


def _break_shortfall_days(db: Session, tenant_id, user, entries, start: date, end: date) -> list:
    """Final-Review (A1-08-Nachzug): Tage mit § 4-Fehlbetrag OHNE anerkannte
    Pausenausnahme.

    § 4 ist an allen Schreibpfaden eine Sperre (#499) — ein Fehlbetrag entsteht
    trotzdem beim Ausstempeln mit beantragter (noch offener oder abgelehnter)
    Ausnahme, beim automatischen Schließen und beim Anerkennen. Bisher stand er
    dann nur im Antragsverlauf oder im Toast von damals. Gerechnet wird wie
    ``validate_daily_break`` über alle geschlossenen Einträge des Tages
    (``break_block_for_entry`` + ``daily_break_figures``); Tage, an denen ein
    Eintrag eine Ausnahme trägt, stehen schon unter ``break_exceptions``."""
    from app.models import ChangeRequest

    by_day: dict = {}
    for e in entries:
        if start <= e.date <= end and e.end_time is not None:
            by_day.setdefault(e.date, []).append(e)
    found = []
    for d in sorted(by_day):
        day_entries = by_day[d]
        if any((e.break_waiver_reason or "").strip() for e in day_entries):
            continue
        blocks = [break_validation_service.break_block_for_entry(db, user, e) for e in day_entries]
        worked, covered = break_validation_service.daily_break_figures(blocks)
        required = 45 if worked > 540 else 30 if worked > 360 else 0
        if covered >= required:
            continue
        requests = (
            db.query(ChangeRequest.status)
            .filter(
                ChangeRequest.tenant_id == tenant_id,  # F-026
                ChangeRequest.time_entry_id.in_([e.id for e in day_entries]),
                ChangeRequest.break_waiver_reason.isnot(None),
            )
            .all()
        )
        statuses = {getattr(r.status, "value", r.status) for r in requests}
        waiver_request = (
            "pending" if "pending" in statuses
            else "rejected" if "rejected" in statuses else None
        )
        found.append({
            "date": d.isoformat(),
            "worked_hours": round(worked / 60.0, 2),
            "break_minutes": int(covered),
            "required_minutes": required,
            "shortfall_minutes": int(required - covered),
            "auto_closed": any(getattr(e, "auto_closed", False) for e in day_entries),
            "credit_override": any(getattr(e, "credit_override", False) for e in day_entries),
            "waiver_request": waiver_request,
        })
    return found


DAILY_LIMIT_MINUTES = 600   # § 3 ArbZG: höchstens 10 h am Werktag
WEEKLY_LIMIT_MINUTES = 2880  # 48 h je Kalenderwoche (§ 3: 6 Werktage × 8 h)


@router.get("/arbzg-limits")
def get_arbzg_limits(
    year: int = Query(..., ge=2000, le=2100, description="Jahr"),
    month: int = Query(None, ge=1, le=12, description="Optionaler Monat"),
    include_hidden: IncludeHidden = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """A1-08 (Audit 2026-11-07): nachträgliche Auswertung — Tage über 10 h, Wochen
    über 48 h und § 4-Pausenausnahmen.

    Beim Ausstempeln ist ein Tag über 10 h bewusst nur eine Warnung (R2-b), dazu
    kommen automatisch geschlossene Einträge, XLS-Import und Anerkennen; eine
    Pausenausnahme steht nur am Eintrag. Ohne diese Liste fand eine Prüfung
    diese Fälle nur über Toasts von damals. Gemessen wird wie im 24-Wochen-
    Bericht: **Anwesenheit laut Stempel** (Rohstempel abzüglich Pausen,
    ``work_window_service.presence_minutes``) und daneben die angerechnete Zeit;
    ein Tag zählt, wenn eine von beiden 10 h übersteigt. Wochen = ISO-Kalender-
    wochen (Mo–So), die den Zeitraum berühren, mit ALLEN ihren Tagen.
    Pausenausnahmen = Einträge mit ``break_waiver_reason`` (Text wie erfasst).
    Pausen-Fehlbeträge = Tage mit § 4-Fehlbetrag ohne Ausnahme
    (``_break_shortfall_days``).
    § 18-befreite Personen erscheinen nicht; aufgeführt werden nur Personen mit
    mindestens einem Befund."""
    if month:
        start, end = date(year, month, 1), date(year, month, monthrange(year, month)[1])
    else:
        start, end = date(year, 1, 1), date(year, 12, 31)
    week_start = start - timedelta(days=start.weekday())
    week_end = end + timedelta(days=6 - end.weekday())
    users, hidden = _arbzg_users(db, current_user.tenant_id, start, end, include_hidden)
    result = []

    for user in users:
        if user.exempt_from_arbzg:
            continue
        entries = (
            db.query(TimeEntry)
            .filter(
                TimeEntry.tenant_id == current_user.tenant_id,  # F-026
                TimeEntry.user_id == user.id,
                TimeEntry.date >= week_start,
                TimeEntry.date <= week_end,
            )
            .order_by(TimeEntry.date, TimeEntry.start_time)
            .all()
        )
        presence_by_day: dict = {}
        credited_by_day: dict = {}
        auto_closed_days: set = set()
        for e in entries:
            presence_by_day[e.date] = presence_by_day.get(e.date, 0) + work_window_service.presence_minutes(e)
            credited_by_day[e.date] = credited_by_day.get(e.date, 0.0) + float(e.net_hours or 0)
            if getattr(e, "auto_closed", False):
                auto_closed_days.add(e.date)

        days_over = []
        for d in sorted(presence_by_day):
            if not (start <= d <= end):
                continue
            presence, credited = presence_by_day[d], credited_by_day[d]
            if presence > DAILY_LIMIT_MINUTES or credited * 60 > DAILY_LIMIT_MINUTES + 1e-6:
                days_over.append({
                    "date": d.isoformat(),
                    "presence_hours": round(presence / 60.0, 2),
                    "credited_hours": round(credited, 2),
                    "auto_closed": d in auto_closed_days,
                })

        by_week: dict = {}
        for d, minutes in presence_by_day.items():
            iso_year, iso_week, _ = d.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
            by_week[key] = by_week.get(key, 0) + minutes
        weeks_over = [
            {"iso_week": key, "presence_hours": round(minutes / 60.0, 2)}
            for key, minutes in sorted(by_week.items())
            if minutes > WEEKLY_LIMIT_MINUTES
        ]

        exceptions = [
            {
                "date": e.date.isoformat(),
                "start_time": e.start_time.strftime("%H:%M"),
                "end_time": e.end_time.strftime("%H:%M") if e.end_time else None,
                "break_minutes": int(e.break_minutes or 0),
                "reason": e.break_waiver_reason.strip(),
            }
            for e in entries
            if start <= e.date <= end and (e.break_waiver_reason or "").strip()
        ]

        shortfalls = _break_shortfall_days(db, current_user.tenant_id, user, entries, start, end)

        if days_over or weeks_over or exceptions or shortfalls:
            result.append({
                "user_id": str(user.id),
                "first_name": user.first_name,
                "last_name": user.last_name,
                "days_over_10h": days_over,
                "weeks_over_48h": weeks_over,
                "break_exceptions": exceptions,
                "break_shortfalls": shortfalls,
            })

    return {
        "year": year,
        "month": month,
        "employees": result,
        "total_days_over_10h": sum(len(r["days_over_10h"]) for r in result),
        "total_weeks_over_48h": sum(len(r["weeks_over_48h"]) for r in result),
        "total_break_exceptions": sum(len(r["break_exceptions"]) for r in result),
        "total_break_shortfalls": sum(len(r["break_shortfalls"]) for r in result),
        "hidden_with_data_count": hidden,
    }
