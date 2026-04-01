"""
ODS (Open Document Spreadsheet) export service.
Mirrors the three Excel exports from export_service.py using odfpy.
Minimal styling: bold headers, no colours – LibreOffice applies its own theme.
"""
from io import BytesIO
from datetime import date, timedelta
from calendar import monthrange
from decimal import Decimal
from typing import List

from sqlalchemy.orm import Session
from sqlalchemy import extract
from odf.opendocument import OpenDocumentSpreadsheet
from odf.style import Style, TextProperties, TableColumnProperties, TableCellProperties
from odf.text import P
from odf.table import Table, TableColumn, TableRow, TableCell

from app.models import User, TimeEntry, Absence, PublicHoliday, AbsenceType
from app.services import calculation_service
from app.services.arbzg_utils import is_night_work


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WEEKDAY_NAMES = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONTH_NAMES = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]
ABSENCE_LABELS = {
    "vacation": "Urlaub",
    "sick": "Krank",
    "training": "Fortbildung",
    "overtime": "Überstundenausgleich",
    "other": "Sonstiges",
}


def _doc_with_styles() -> tuple:
    """Return (doc, bold_style, normal_style)."""
    doc = OpenDocumentSpreadsheet()

    bold = Style(name="Bold", family="table-cell")
    bold.addElement(TextProperties(fontweight="bold"))
    doc.styles.addElement(bold)

    normal = Style(name="Normal", family="table-cell")
    doc.styles.addElement(normal)

    return doc, bold, normal


def _str_cell(value: str, style=None) -> TableCell:
    cell = TableCell(valuetype="string", stylename=style)
    cell.addElement(P(text=str(value) if value is not None else ""))
    return cell


def _float_cell(value: float, style=None) -> TableCell:
    cell = TableCell(valuetype="float", value=str(round(value, 2)), stylename=style)
    cell.addElement(P(text=f"{value:.2f}"))
    return cell


def _int_cell(value: int, style=None) -> TableCell:
    cell = TableCell(valuetype="float", value=str(value), stylename=style)
    cell.addElement(P(text=str(value)))
    return cell


def _empty_cell() -> TableCell:
    return TableCell(valuetype="string")


def _header_row(columns: List[str], bold_style) -> TableRow:
    tr = TableRow()
    for col in columns:
        tr.addElement(_str_cell(col, style=bold_style))
    return tr


def _save(doc: OpenDocumentSpreadsheet) -> BytesIO:
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def _get_active_users(db: Session) -> List[User]:
    return (
        db.query(User)
        .filter(User.is_active == True)
        .order_by(User.last_name, User.first_name)
        .all()
    )


# ---------------------------------------------------------------------------
# Monthly report
# ---------------------------------------------------------------------------

def generate_monthly_report(db: Session, year: int, month: int, include_health_data: bool = False) -> BytesIO:
    """One sheet per employee, daily rows with target/actual/diff.
    DSGVO F-003: sick absences are masked when include_health_data=False (default)."""
    doc, bold, normal = _doc_with_styles()

    users = _get_active_users(db)
    for user in users:
        _monthly_sheet(doc, db, user, year, month, bold, normal, include_health_data)

    return _save(doc)


def _monthly_sheet(doc, db, user, year, month, bold, normal, include_health_data: bool = False):
    sheet_name = f"{user.last_name} {user.first_name}"[:31]
    table = Table(name=sheet_name)
    doc.spreadsheet.addElement(table)

    # Rows 1–2: ArbZG-relevante Mitarbeiter-Metadaten
    meta1 = TableRow()
    meta1.addElement(_str_cell("Mitarbeiter:", style=bold))
    meta1.addElement(_str_cell(f"{user.first_name} {user.last_name}"))
    meta1.addElement(_empty_cell())
    meta1.addElement(_str_cell("Wochenstunden:", style=bold))
    meta1.addElement(_float_cell(float(user.weekly_hours)))
    meta1.addElement(_empty_cell())
    meta1.addElement(_str_cell("Monat:", style=bold))
    meta1.addElement(_str_cell(f"{month:02d}/{year}"))
    table.addElement(meta1)

    meta2 = TableRow()
    meta2.addElement(_str_cell("§18 ArbZG-befreit:", style=bold))
    meta2.addElement(_str_cell("Ja" if user.exempt_from_arbzg else "Nein"))
    meta2.addElement(_empty_cell())
    meta2.addElement(_str_cell("Nachtarbeitnehmer (§6 Abs. 2 ArbZG):", style=bold))
    meta2.addElement(_str_cell("Ja" if user.is_night_worker else "Nein"))
    table.addElement(meta2)

    table.addElement(TableRow())  # Blank separator

    headers = [
        "Datum", "Wochentag", "Von", "Bis", "Pause (Min)",
        "Netto (Std)", "Soll (Std)", "Differenz", "Abwesenheit", "Bemerkung",
    ]
    table.addElement(_header_row(headers, bold))

    _, last_day = monthrange(year, month)

    entries_by_date: dict = {}
    for e in db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        extract("year", TimeEntry.date) == year,
        extract("month", TimeEntry.date) == month,
    ).order_by(TimeEntry.start_time).all():
        entries_by_date.setdefault(e.date, []).append(e)
    absences_by_date = {
        a.date: a
        for a in db.query(Absence).filter(
            Absence.user_id == user.id,
            extract("year", Absence.date) == year,
            extract("month", Absence.date) == month,
        ).all()
    }
    holidays_by_date = {
        h.date: h
        for h in db.query(PublicHoliday).filter(
            extract("year", PublicHoliday.date) == year,
            extract("month", PublicHoliday.date) == month,
        ).all()
    }

    total_net = Decimal("0.00")
    total_target = Decimal("0.00")
    night_work_count = 0

    for day in range(1, last_day + 1):
        current_date = date(year, month, day)
        weekday = current_date.weekday()
        is_sunday = weekday == 6
        is_weekend = weekday >= 5
        is_holiday = current_date in holidays_by_date
        absence = absences_by_date.get(current_date)
        day_entries = entries_by_date.get(current_date, [])

        # Night work check (§6 / §2 Abs. 4 ArbZG)
        is_night_wrk = any(
            e.end_time is not None and is_night_work(e.start_time, e.end_time)
            for e in day_entries
        )
        if is_night_wrk:
            night_work_count += 1

        tr = TableRow()
        tr.addElement(_str_cell(current_date.strftime("%d.%m.%Y")))
        tr.addElement(_str_cell(WEEKDAY_NAMES[weekday]))

        if day_entries:
            first_start = day_entries[0].start_time
            last_end = day_entries[-1].end_time
            total_break = sum(e.break_minutes or 0 for e in day_entries)
            total_day_net = sum(e.net_hours for e in day_entries)
            tr.addElement(_str_cell(first_start.strftime("%H:%M")))
            tr.addElement(_str_cell(last_end.strftime("%H:%M") if last_end else "offen"))
            tr.addElement(_int_cell(total_break))
            tr.addElement(_float_cell(float(total_day_net)))
            net = total_day_net
            total_net += net
        else:
            tr.addElement(_empty_cell())
            tr.addElement(_empty_cell())
            tr.addElement(_empty_cell())
            tr.addElement(_float_cell(0.0))
            net = Decimal("0.00")

        # Per-day target using historical weekly hours
        weekly_hours = calculation_service.get_weekly_hours_for_date(db, user, current_date)
        daily_target = calculation_service.get_daily_target_for_date(user, current_date, weekly_hours=weekly_hours)

        # Soll + Abwesenheit + Bemerkung
        if is_weekend:
            target = Decimal("0.00")
            if is_sunday and day_entries:
                abw = "Sonntagsarbeit (§9/§10 ArbZG)"
            elif is_sunday:
                abw = "Sonntag"
            else:
                abw = "Samstag"
            if is_night_wrk:
                abw += " | Nachtarbeit (§6 ArbZG)"
            tr.addElement(_float_cell(0.0))
            tr.addElement(_float_cell(0.0))
            tr.addElement(_str_cell(abw))
            # Bemerkung: §10-Ausnahmegrund wenn vorhanden
            bem_parts = []
            for e in day_entries:
                if e.sunday_exception_reason:
                    bem_parts.append(f"§10-Ausnahmegrund: {e.sunday_exception_reason}")
                elif e.note:
                    bem_parts.append(e.note)
            tr.addElement(_str_cell(" | ".join(bem_parts) if bem_parts else ""))
        elif is_holiday:
            target = Decimal("0.00")
            holiday = holidays_by_date[current_date]
            if day_entries:
                abw = f"Feiertagsarbeit: {holiday.name} (§9/§10 ArbZG)"
            else:
                abw = f"Feiertag: {holiday.name}"
            if is_night_wrk:
                abw += " | Nachtarbeit (§6 ArbZG)"
            tr.addElement(_float_cell(0.0))
            tr.addElement(_float_cell(0.0))
            tr.addElement(_str_cell(abw))
            bem_parts = []
            for e in day_entries:
                if e.sunday_exception_reason:
                    bem_parts.append(f"§10-Ausnahmegrund: {e.sunday_exception_reason}")
                if e.note:
                    bem_parts.append(e.note)
            tr.addElement(_str_cell(" | ".join(bem_parts) if bem_parts else ""))
        elif absence:
            target = Decimal("0.00")
            # DSGVO F-003: mask sick absences unless health data explicitly requested
            if absence.type.value == "sick" and not include_health_data:
                label = "Abwesenheit"
                note_str = ""
            else:
                label = ABSENCE_LABELS.get(absence.type.value, absence.type.value)
                note_str = absence.note or ""
            tr.addElement(_float_cell(0.0))
            tr.addElement(_float_cell(0.0))
            tr.addElement(_str_cell(f"{label} ({float(absence.hours):.1f}h)"))
            tr.addElement(_str_cell(note_str))
        else:
            target = daily_target
            diff = float(net - target)
            tr.addElement(_float_cell(float(target)))
            tr.addElement(_float_cell(diff))
            abw = "Nachtarbeit (§6 ArbZG)" if is_night_wrk else ""
            tr.addElement(_str_cell(abw))
            notes = " | ".join(e.note for e in day_entries if e.note)
            tr.addElement(_str_cell(notes))

        total_target += target
        table.addElement(tr)

    # Summary rows
    table.addElement(TableRow())  # blank

    def summary_row(label: str, value: float) -> TableRow:
        tr = TableRow()
        tr.addElement(_str_cell(label, style=bold))
        tr.addElement(_float_cell(value))
        return tr

    def summary_int_row(label: str, value: int) -> TableRow:
        tr = TableRow()
        tr.addElement(_str_cell(label, style=bold))
        tr.addElement(_int_cell(value))
        return tr

    table.addElement(summary_row("Soll-Stunden Monat:", float(total_target)))
    table.addElement(summary_row("Ist-Stunden Monat:", float(total_net)))
    table.addElement(summary_row("Saldo Monat:", float(total_net - total_target)))

    overtime = calculation_service.get_overtime_account(db, user, year, month)
    table.addElement(summary_row("Überstunden kumuliert:", float(overtime)))

    vac = calculation_service.get_vacation_account(db, user, year)
    table.addElement(summary_row("Urlaub genommen (Std):", float(vac["used_hours"])))
    table.addElement(summary_row("Urlaub Rest (Std):", float(vac["remaining_hours"])))
    table.addElement(summary_int_row("Nachtarbeitstage (§6 ArbZG):", night_work_count))


# ---------------------------------------------------------------------------
# Yearly detailed report
# ---------------------------------------------------------------------------

def generate_yearly_report(db: Session, year: int) -> BytesIO:
    """Overview + absences overview + one detail sheet per employee (365 days)."""
    doc, bold, normal = _doc_with_styles()

    users = _get_active_users(db)
    _yearly_overview_sheet(doc, db, users, year, bold)
    _absences_overview_sheet(doc, db, users, year, bold)
    for user in users:
        _yearly_employee_sheet(doc, db, user, year, bold)

    return _save(doc)


def _yearly_overview_sheet(doc, db, users, year, bold):
    table = Table(name="Jahresübersicht")
    doc.spreadsheet.addElement(table)

    headers = [
        "Mitarbeiter", "Wochenstunden",
        "Soll (Std)", "Ist (Std)", "Saldo (Std)",
        "Überstunden kum.", "Urlaub (Std)", "Krank (Std)",
    ]
    table.addElement(_header_row(headers, bold))

    for user in users:
        target = sum(
            float(calculation_service.get_monthly_target(db, user, year, m))
            for m in range(1, 13)
        )
        actual = sum(
            float(calculation_service.get_monthly_actual(db, user, year, m))
            for m in range(1, 13)
        )
        overtime = float(calculation_service.get_overtime_account(db, user, year, 12))

        vac_h = sum(
            float(a.hours)
            for a in db.query(Absence).filter(
                Absence.user_id == user.id,
                Absence.type == AbsenceType.VACATION,
                extract("year", Absence.date) == year,
            ).all()
        )
        sick_h = sum(
            float(a.hours)
            for a in db.query(Absence).filter(
                Absence.user_id == user.id,
                Absence.type == AbsenceType.SICK,
                extract("year", Absence.date) == year,
            ).all()
        )

        tr = TableRow()
        tr.addElement(_str_cell(f"{user.last_name}, {user.first_name}"))
        tr.addElement(_float_cell(float(user.weekly_hours)))
        tr.addElement(_float_cell(target))
        tr.addElement(_float_cell(actual))
        tr.addElement(_float_cell(actual - target))
        tr.addElement(_float_cell(overtime))
        tr.addElement(_float_cell(vac_h))
        tr.addElement(_float_cell(sick_h))
        table.addElement(tr)


def _absences_overview_sheet(doc, db, users, year, bold):
    table = Table(name="Abwesenheiten")
    doc.spreadsheet.addElement(table)

    headers = [
        "Mitarbeiter",
        "Urlaub (Tage)", "Krank (Tage)", "Fortbildung (Tage)",
        "ÜStd.-Ausgleich (Tage)", "Sonstiges (Tage)",
        "Gesamt (Tage)", "Resturlaub (Tage)",
    ]
    table.addElement(_header_row(headers, bold))

    for user in users:
        # Uses current daily target for hours-to-days conversion — approximate for display
        dt = float(calculation_service.get_daily_target(user)) or 8.0

        def days(atype):
            return sum(
                float(a.hours)
                for a in db.query(Absence).filter(
                    Absence.user_id == user.id,
                    Absence.type == atype,
                    extract("year", Absence.date) == year,
                ).all()
            ) / dt

        vac = days(AbsenceType.VACATION)
        sick = days(AbsenceType.SICK)
        train = days(AbsenceType.TRAINING)
        overtime_comp = days(AbsenceType.OVERTIME)
        other = days(AbsenceType.OTHER)

        vac_acc = calculation_service.get_vacation_account(db, user, year)
        remaining = float(vac_acc["remaining_days"])

        tr = TableRow()
        tr.addElement(_str_cell(f"{user.last_name}, {user.first_name}"))
        tr.addElement(_float_cell(vac))
        tr.addElement(_float_cell(sick))
        tr.addElement(_float_cell(train))
        tr.addElement(_float_cell(overtime_comp))
        tr.addElement(_float_cell(other))
        tr.addElement(_float_cell(vac + sick + train + overtime_comp + other))
        tr.addElement(_float_cell(remaining))
        table.addElement(tr)


def _yearly_employee_sheet(doc, db, user, year, bold):
    sheet_name = f"{user.last_name} {user.first_name}"[:31]
    table = Table(name=sheet_name)
    doc.spreadsheet.addElement(table)

    # ArbZG-relevante Metadaten
    meta1 = TableRow()
    meta1.addElement(_str_cell("§18 ArbZG-befreit:", style=bold))
    meta1.addElement(_str_cell("Ja" if user.exempt_from_arbzg else "Nein"))
    meta1.addElement(_empty_cell())
    meta1.addElement(_str_cell("Nachtarbeitnehmer (§6 Abs. 2 ArbZG):", style=bold))
    meta1.addElement(_str_cell("Ja" if user.is_night_worker else "Nein"))
    table.addElement(meta1)
    table.addElement(TableRow())  # blank

    headers = [
        "Datum", "Wochentag", "Von", "Bis", "Pause (Min)",
        "Netto (Std)", "Soll (Std)", "Differenz", "Abwesenheit", "Bemerkung",
    ]
    table.addElement(_header_row(headers, bold))

    entries_by_date: dict = {}
    for e in db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        extract("year", TimeEntry.date) == year,
    ).order_by(TimeEntry.start_time).all():
        entries_by_date.setdefault(e.date, []).append(e)
    absences_by_date = {
        a.date: a
        for a in db.query(Absence).filter(
            Absence.user_id == user.id,
            extract("year", Absence.date) == year,
        ).all()
    }
    holidays_by_date = {
        h.date: h
        for h in db.query(PublicHoliday).filter(
            extract("year", PublicHoliday.date) == year,
        ).all()
    }

    current_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    night_work_count = 0

    while current_date <= end_date:
        weekday = current_date.weekday()
        is_sunday = weekday == 6
        is_weekend = weekday >= 5
        is_holiday = current_date in holidays_by_date
        absence = absences_by_date.get(current_date)
        day_entries = entries_by_date.get(current_date, [])
        weekly_hours = calculation_service.get_weekly_hours_for_date(db, user, current_date)
        daily_target = calculation_service.get_daily_target_for_date(user, current_date, weekly_hours=weekly_hours)

        # Night work check (§6 / §2 Abs. 4 ArbZG)
        is_night_wrk = any(
            e.end_time is not None and is_night_work(e.start_time, e.end_time)
            for e in day_entries
        )
        if is_night_wrk:
            night_work_count += 1

        tr = TableRow()
        tr.addElement(_str_cell(current_date.strftime("%d.%m.%Y")))
        tr.addElement(_str_cell(WEEKDAY_NAMES[weekday]))

        if day_entries:
            first_start = day_entries[0].start_time
            last_end = day_entries[-1].end_time
            total_break = sum(e.break_minutes or 0 for e in day_entries)
            total_day_net = sum(float(e.net_hours) for e in day_entries)
            tr.addElement(_str_cell(first_start.strftime("%H:%M")))
            tr.addElement(_str_cell(last_end.strftime("%H:%M") if last_end else "offen"))
            tr.addElement(_int_cell(total_break))
            tr.addElement(_float_cell(total_day_net))
            net = total_day_net
        else:
            tr.addElement(_empty_cell())
            tr.addElement(_empty_cell())
            tr.addElement(_empty_cell())
            tr.addElement(_float_cell(0.0))
            net = 0.0

        if is_weekend:
            if is_sunday and day_entries:
                abw = "Sonntagsarbeit (§9/§10 ArbZG)"
            elif is_sunday:
                abw = "Sonntag"
            else:
                abw = "Samstag"
            if is_night_wrk:
                abw += " | Nachtarbeit (§6 ArbZG)"
            tr.addElement(_float_cell(0.0))
            tr.addElement(_float_cell(0.0))
            tr.addElement(_str_cell(abw))
            bem_parts = []
            for e in day_entries:
                if e.sunday_exception_reason:
                    bem_parts.append(f"§10-Ausnahmegrund: {e.sunday_exception_reason}")
                elif e.note:
                    bem_parts.append(e.note)
            tr.addElement(_str_cell(" | ".join(bem_parts) if bem_parts else ""))
        elif is_holiday:
            holiday = holidays_by_date[current_date]
            if day_entries:
                abw = f"Feiertagsarbeit: {holiday.name} (§9/§10 ArbZG)"
            else:
                abw = f"Feiertag: {holiday.name}"
            if is_night_wrk:
                abw += " | Nachtarbeit (§6 ArbZG)"
            tr.addElement(_float_cell(0.0))
            tr.addElement(_float_cell(0.0))
            tr.addElement(_str_cell(abw))
            bem_parts = []
            for e in day_entries:
                if e.sunday_exception_reason:
                    bem_parts.append(f"§10-Ausnahmegrund: {e.sunday_exception_reason}")
                if e.note:
                    bem_parts.append(e.note)
            tr.addElement(_str_cell(" | ".join(bem_parts) if bem_parts else ""))
        elif absence:
            label = ABSENCE_LABELS.get(absence.type.value, absence.type.value)
            tr.addElement(_float_cell(0.0))
            tr.addElement(_float_cell(0.0))
            tr.addElement(_str_cell(f"{label} ({float(absence.hours):.1f}h)"))
            tr.addElement(_str_cell(absence.note or ""))
        else:
            target = float(daily_target)
            tr.addElement(_float_cell(target))
            tr.addElement(_float_cell(net - target))
            abw = "Nachtarbeit (§6 ArbZG)" if is_night_wrk else ""
            tr.addElement(_str_cell(abw))
            notes = " | ".join(e.note for e in day_entries if e.note)
            tr.addElement(_str_cell(notes))

        table.addElement(tr)
        current_date += timedelta(days=1)


# ---------------------------------------------------------------------------
# Yearly classic report (compact – one row per month)
# ---------------------------------------------------------------------------

def generate_yearly_report_classic(db: Session, year: int) -> BytesIO:
    """One sheet per employee, 12 rows (one per month)."""
    doc, bold, normal = _doc_with_styles()

    users = _get_active_users(db)
    for user in users:
        _classic_sheet(doc, db, user, year, bold)

    return _save(doc)


def _classic_sheet(doc, db, user, year, bold):
    sheet_name = f"{user.last_name} {user.first_name}"[:31]
    table = Table(name=sheet_name)
    doc.spreadsheet.addElement(table)

    # Title row
    title_tr = TableRow()
    title_tr.addElement(_str_cell(f"{user.first_name} {user.last_name} – Jahresübersicht {year}", style=bold))
    table.addElement(title_tr)

    # ArbZG-Flags
    flags_tr = TableRow()
    flags_tr.addElement(_str_cell("§18 ArbZG-befreit:", style=bold))
    flags_tr.addElement(_str_cell("Ja" if user.exempt_from_arbzg else "Nein"))
    flags_tr.addElement(_empty_cell())
    flags_tr.addElement(_str_cell("Nachtarbeitnehmer (§6 Abs. 2 ArbZG):", style=bold))
    flags_tr.addElement(_str_cell("Ja" if user.is_night_worker else "Nein"))
    table.addElement(flags_tr)
    table.addElement(TableRow())  # blank

    headers = [
        "Monat", "Soll (Std)", "Ist (Std)", "Saldo (Std)",
        "Urlaub (Std)", "Krank (Std)", "Fortbildung (Std)", "Sonstiges (Std)", "Nachtarbeit-Tage (§6)",
    ]
    table.addElement(_header_row(headers, bold))

    total_target = 0.0
    total_actual = 0.0
    total_vac = 0.0
    total_sick = 0.0
    total_train = 0.0
    total_other = 0.0

    for m in range(1, 13):
        target = float(calculation_service.get_monthly_target(db, user, year, m))
        actual = float(calculation_service.get_monthly_actual(db, user, year, m))

        def month_absence_hours(atype):
            return sum(
                float(a.hours)
                for a in db.query(Absence).filter(
                    Absence.user_id == user.id,
                    Absence.type == atype,
                    extract("year", Absence.date) == year,
                    extract("month", Absence.date) == m,
                ).all()
            )

        vac = month_absence_hours(AbsenceType.VACATION)
        sick = month_absence_hours(AbsenceType.SICK)
        train = month_absence_hours(AbsenceType.TRAINING)
        other = month_absence_hours(AbsenceType.OTHER)

        total_target += target
        total_actual += actual
        total_vac += vac
        total_sick += sick
        total_train += train
        total_other += other

        # Night work days for this month (§6 ArbZG)
        month_entries = db.query(TimeEntry).filter(
            TimeEntry.user_id == user.id,
            extract("year", TimeEntry.date) == year,
            extract("month", TimeEntry.date) == m,
            TimeEntry.end_time.isnot(None),
        ).all()
        night_days = len({e.date for e in month_entries if is_night_work(e.start_time, e.end_time)})

        tr = TableRow()
        tr.addElement(_str_cell(MONTH_NAMES[m - 1]))
        tr.addElement(_float_cell(target))
        tr.addElement(_float_cell(actual))
        tr.addElement(_float_cell(actual - target))
        tr.addElement(_float_cell(vac))
        tr.addElement(_float_cell(sick))
        tr.addElement(_float_cell(train))
        tr.addElement(_float_cell(other))
        tr.addElement(_int_cell(night_days))
        table.addElement(tr)

    # Total row (night work total counted over all months)
    total_night = len({
        e.date for e in db.query(TimeEntry).filter(
            TimeEntry.user_id == user.id,
            extract("year", TimeEntry.date) == year,
            TimeEntry.end_time.isnot(None),
        ).all()
        if is_night_work(e.start_time, e.end_time)
    })
    tr = TableRow()
    tr.addElement(_str_cell("Gesamt", style=bold))
    tr.addElement(_float_cell(total_target))
    tr.addElement(_float_cell(total_actual))
    tr.addElement(_float_cell(total_actual - total_target))
    tr.addElement(_float_cell(total_vac))
    tr.addElement(_float_cell(total_sick))
    tr.addElement(_float_cell(total_train))
    tr.addElement(_float_cell(total_other))
    tr.addElement(_int_cell(total_night))
    table.addElement(tr)

    table.addElement(TableRow())

    # Overtime + vacation summary
    overtime = float(calculation_service.get_overtime_account(db, user, year, 12))
    vac_acc = calculation_service.get_vacation_account(db, user, year)

    def summary_row(label, value):
        tr2 = TableRow()
        tr2.addElement(_str_cell(label, style=bold))
        tr2.addElement(_float_cell(value))
        return tr2

    table.addElement(summary_row("Überstunden kumuliert (Jahresende):", overtime))
    table.addElement(summary_row("Urlaub Budget (Std):", float(vac_acc["budget_hours"])))
    table.addElement(summary_row("Urlaub genommen (Std):", float(vac_acc["used_hours"])))
    table.addElement(summary_row("Urlaub Rest (Std):", float(vac_acc["remaining_hours"])))
