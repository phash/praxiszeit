from io import BytesIO
from datetime import date, datetime, timedelta
from calendar import monthrange
from decimal import Decimal
from typing import List
from sqlalchemy.orm import Session
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from app.models import User, TimeEntry, Absence, PublicHoliday, AbsenceType
from app.services import calculation_service
from sqlalchemy import extract

_NIGHT_THRESHOLD_MINUTES = 120  # §2 Abs. 4 ArbZG: mind. 2h Nachtzeit = Nachtarbeit


def _is_night_work_export(start_time, end_time) -> bool:
    """True wenn >2h Nachtzeit (23:00–06:00), §2 Abs. 4 / §6 ArbZG."""
    if not start_time or not end_time:
        return False

    def to_min(t) -> int:
        return t.hour * 60 + t.minute

    s, e = to_min(start_time), to_min(end_time)
    if e <= s:
        e += 1440  # Mitternachtsübergang
    nm = (max(0, min(e, 360) - max(s, 0))       # 00:00–06:00
          + max(0, min(e, 1440) - max(s, 1380))  # 23:00–24:00
          + max(0, min(e, 1800) - max(s, 1440))) # 00:00–06:00 (Folgetag)
    return nm > _NIGHT_THRESHOLD_MINUTES


def generate_monthly_report(db: Session, year: int, month: int) -> BytesIO:
    """
    Generate Excel report for all employees for a given month.
    Creates one sheet per employee.

    Args:
        db: Database session
        year: Year
        month: Month (1-12)

    Returns:
        BytesIO object containing Excel file
    """
    wb = Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Get all active employees
    users = db.query(User).filter(User.is_active == True).order_by(User.last_name, User.first_name).all()

    for user in users:
        _create_employee_sheet(wb, db, user, year, month)

    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output


def _create_employee_sheet(wb: Workbook, db: Session, user: User, year: int, month: int):
    """
    Create a worksheet for a single employee.

    Columns:
    - Datum
    - Wochentag
    - Von
    - Bis
    - Pause (Min)
    - Netto (Std)
    - Soll (Std)
    - Differenz
    - Abwesenheit
    - Bemerkung
    """
    sheet = wb.create_sheet(title=f"{user.last_name} {user.first_name}"[:31])  # Excel sheet name max 31 chars

    # Row 1–2: ArbZG-relevante Mitarbeiter-Metadaten (§16 ArbZG Aufzeichnungspflicht)
    sheet.cell(row=1, column=1).value = "Mitarbeiter:"
    sheet.cell(row=1, column=1).font = Font(bold=True)
    sheet.cell(row=1, column=2).value = f"{user.first_name} {user.last_name}"
    sheet.cell(row=1, column=4).value = "Wochenstunden:"
    sheet.cell(row=1, column=4).font = Font(bold=True)
    sheet.cell(row=1, column=5).value = float(user.weekly_hours)
    sheet.cell(row=1, column=7).value = "Monat:"
    sheet.cell(row=1, column=7).font = Font(bold=True)
    sheet.cell(row=1, column=8).value = f"{month:02d}/{year}"
    sheet.cell(row=2, column=1).value = "§18 ArbZG-befreit:"
    sheet.cell(row=2, column=1).font = Font(bold=True)
    sheet.cell(row=2, column=2).value = "Ja" if user.exempt_from_arbzg else "Nein"
    sheet.cell(row=2, column=4).value = "Nachtarbeitnehmer (§6 Abs. 2 ArbZG):"
    sheet.cell(row=2, column=4).font = Font(bold=True)
    sheet.cell(row=2, column=5).value = "Ja" if user.is_night_worker else "Nein"
    # Row 3: blank separator

    # Row 4: Column headers
    headers = ["Datum", "Wochentag", "Von", "Bis", "Pause (Min)", "Netto (Std)", "Soll (Std)", "Differenz", "Abwesenheit", "Bemerkung"]
    for col_num, header in enumerate(headers, 1):
        cell = sheet.cell(row=4, column=col_num)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCE5FF", end_color="CCE5FF", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    # Get data
    _, last_day = monthrange(year, month)
    daily_target = calculation_service.get_daily_target(user)

    # Get all time entries for the month
    time_entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        extract('year', TimeEntry.date) == year,
        extract('month', TimeEntry.date) == month
    ).all()
    entries_by_date = {entry.date: entry for entry in time_entries}

    # Get all absences for the month
    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        extract('year', Absence.date) == year,
        extract('month', Absence.date) == month
    ).all()
    absences_by_date = {absence.date: absence for absence in absences}

    # Get public holidays
    holidays = db.query(PublicHoliday).filter(
        extract('year', PublicHoliday.date) == year,
        extract('month', PublicHoliday.date) == month
    ).all()
    holidays_by_date = {holiday.date: holiday for holiday in holidays}

    # German weekday names
    weekday_names = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

    row = 5  # Data starts after 3-row header + blank
    total_net = Decimal('0.00')
    total_target = Decimal('0.00')
    night_work_count = 0

    # Iterate through all days of the month
    for day in range(1, last_day + 1):
        current_date = date(year, month, day)
        weekday = current_date.weekday()
        weekday_name = weekday_names[weekday]
        is_sunday = weekday == 6

        # Check if it's a weekend, holiday, or absence
        is_weekend = weekday >= 5
        is_holiday = current_date in holidays_by_date
        absence = absences_by_date.get(current_date)

        # Date column
        sheet.cell(row=row, column=1).value = current_date
        sheet.cell(row=row, column=1).number_format = 'DD.MM.YYYY'

        # Weekday column
        sheet.cell(row=row, column=2).value = weekday_name

        # Get time entry if exists
        entry = entries_by_date.get(current_date)

        # Night work check (§6 / §2 Abs. 4 ArbZG)
        is_night_wrk = (entry is not None and entry.end_time is not None
                        and _is_night_work_export(entry.start_time, entry.end_time))
        if is_night_wrk:
            night_work_count += 1

        if entry:
            sheet.cell(row=row, column=3).value = entry.start_time.strftime('%H:%M')
            sheet.cell(row=row, column=4).value = entry.end_time.strftime('%H:%M') if entry.end_time else 'offen'
            sheet.cell(row=row, column=5).value = entry.break_minutes
            sheet.cell(row=row, column=6).value = float(entry.net_hours)
            sheet.cell(row=row, column=6).number_format = '0.00'
            # Bemerkung (col 10): §10-Ausnahmegrund hat Vorrang, dann entry.note
            bemerkung_parts = []
            if entry.sunday_exception_reason and (is_sunday or is_holiday):
                bemerkung_parts.append(f"§10-Ausnahmegrund: {entry.sunday_exception_reason}")
            if entry.note:
                bemerkung_parts.append(entry.note)
            if bemerkung_parts:
                sheet.cell(row=row, column=10).value = " | ".join(bemerkung_parts)
            net = entry.net_hours
            total_net += net
        else:
            net = Decimal('0.00')
            sheet.cell(row=row, column=6).value = 0.00
            sheet.cell(row=row, column=6).number_format = '0.00'

        # Target hours + Abwesenheit (col 9) – korrekte Labels für §9/§10/§6
        if is_weekend:
            target = Decimal('0.00')
            if is_sunday and entry:
                abw = "Sonntagsarbeit (§9/§10 ArbZG)"
            elif is_sunday:
                abw = "Sonntag"
            else:
                abw = "Samstag"
            if is_night_wrk:
                abw += " | Nachtarbeit (§6 ArbZG)"
            sheet.cell(row=row, column=9).value = abw
            for col in range(1, 11):
                sheet.cell(row=row, column=col).fill = PatternFill(start_color="E8E8E8", end_color="E8E8E8", fill_type="solid")
        elif is_holiday:
            target = Decimal('0.00')
            holiday = holidays_by_date[current_date]
            if entry:
                abw = f"Feiertagsarbeit: {holiday.name} (§9/§10 ArbZG)"
            else:
                abw = f"Feiertag: {holiday.name}"
            if is_night_wrk:
                abw += " | Nachtarbeit (§6 ArbZG)"
            sheet.cell(row=row, column=9).value = abw
            # col 10 (Bemerkung) bereits oben gesetzt – NICHT mit holiday.name überschreiben
            for col in range(1, 11):
                sheet.cell(row=row, column=col).fill = PatternFill(start_color="FFFFCC", end_color="FFFFCC", fill_type="solid")
        elif absence:
            target = Decimal('0.00')
            absence_type_map = {
                "vacation": "Urlaub",
                "sick": "Krank",
                "training": "Fortbildung",
                "other": "Sonstiges"
            }
            type_name = absence_type_map.get(absence.type.value, absence.type.value)
            sheet.cell(row=row, column=9).value = f"{type_name} ({float(absence.hours)}h)"
            if absence.note:
                sheet.cell(row=row, column=10).value = absence.note
        else:
            # Regulärer Arbeitstag
            target = daily_target
            if is_night_wrk:
                sheet.cell(row=row, column=9).value = "Nachtarbeit (§6 ArbZG)"

        sheet.cell(row=row, column=7).value = float(target)
        sheet.cell(row=row, column=7).number_format = '0.00'
        total_target += target

        # Difference
        diff = net - target
        sheet.cell(row=row, column=8).value = float(diff)
        sheet.cell(row=row, column=8).number_format = '0.00'

        if diff > 0:
            sheet.cell(row=row, column=8).font = Font(color="006400")
        elif diff < 0:
            sheet.cell(row=row, column=8).font = Font(color="8B0000")

        row += 1

    # Summary section
    row += 1
    sheet.cell(row=row, column=1).value = "Zusammenfassung"
    sheet.cell(row=row, column=1).font = Font(bold=True, size=12)

    row += 1
    sheet.cell(row=row, column=1).value = "Soll-Stunden Monat:"
    sheet.cell(row=row, column=2).value = float(total_target)
    sheet.cell(row=row, column=2).number_format = '0.00'
    sheet.cell(row=row, column=1).font = Font(bold=True)

    row += 1
    sheet.cell(row=row, column=1).value = "Ist-Stunden Monat:"
    sheet.cell(row=row, column=2).value = float(total_net)
    sheet.cell(row=row, column=2).number_format = '0.00'
    sheet.cell(row=row, column=1).font = Font(bold=True)

    row += 1
    monthly_balance = total_net - total_target
    sheet.cell(row=row, column=1).value = "Saldo Monat:"
    sheet.cell(row=row, column=2).value = float(monthly_balance)
    sheet.cell(row=row, column=2).number_format = '0.00'
    sheet.cell(row=row, column=1).font = Font(bold=True)
    if monthly_balance > 0:
        sheet.cell(row=row, column=2).font = Font(bold=True, color="006400")
    elif monthly_balance < 0:
        sheet.cell(row=row, column=2).font = Font(bold=True, color="8B0000")

    row += 1
    overtime_account = calculation_service.get_overtime_account(db, user, year, month)
    sheet.cell(row=row, column=1).value = "Überstunden kumuliert:"
    sheet.cell(row=row, column=2).value = float(overtime_account)
    sheet.cell(row=row, column=2).number_format = '0.00'
    sheet.cell(row=row, column=1).font = Font(bold=True)
    if overtime_account > 0:
        sheet.cell(row=row, column=2).font = Font(bold=True, color="006400")
    elif overtime_account < 0:
        sheet.cell(row=row, column=2).font = Font(bold=True, color="8B0000")

    row += 1
    vacation_account = calculation_service.get_vacation_account(db, user, year)
    sheet.cell(row=row, column=1).value = "Urlaub genommen (Std):"
    sheet.cell(row=row, column=2).value = float(vacation_account['used_hours'])
    sheet.cell(row=row, column=2).number_format = '0.00'

    row += 1
    sheet.cell(row=row, column=1).value = "Urlaub Rest (Std):"
    sheet.cell(row=row, column=2).value = float(vacation_account['remaining_hours'])
    sheet.cell(row=row, column=2).number_format = '0.00'

    row += 1
    sheet.cell(row=row, column=1).value = "Nachtarbeitstage (§6 ArbZG):"
    sheet.cell(row=row, column=2).value = night_work_count
    sheet.cell(row=row, column=1).font = Font(bold=True)

    # Adjust column widths
    sheet.column_dimensions['A'].width = 12
    sheet.column_dimensions['B'].width = 10
    sheet.column_dimensions['C'].width = 8
    sheet.column_dimensions['D'].width = 8
    sheet.column_dimensions['E'].width = 12
    sheet.column_dimensions['F'].width = 12
    sheet.column_dimensions['G'].width = 12
    sheet.column_dimensions['H'].width = 10
    sheet.column_dimensions['I'].width = 28
    sheet.column_dimensions['J'].width = 35


def generate_yearly_report(db: Session, year: int) -> BytesIO:
    """
    Generate Excel report for all employees for a given year.
    Creates:
    - Overview sheet with summary for all employees
    - One sheet per employee with monthly breakdown
    - Absences overview

    Args:
        db: Database session
        year: Year

    Returns:
        BytesIO object containing Excel file
    """
    wb = Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Get all active employees
    users = db.query(User).filter(User.is_active == True).order_by(User.last_name, User.first_name).all()

    # Create overview sheet
    _create_yearly_overview_sheet(wb, db, users, year)

    # Create absences overview sheet
    _create_absences_overview_sheet(wb, db, users, year)

    # Create employee detail sheets
    for user in users:
        _create_employee_yearly_sheet(wb, db, user, year)

    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output


def _create_yearly_overview_sheet(wb: Workbook, db: Session, users: List[User], year: int):
    """Create overview sheet with all employees."""
    sheet = wb.create_sheet(title="Jahresübersicht", index=0)

    # Title
    sheet.cell(row=1, column=1).value = f"Jahresübersicht {year}"
    sheet.cell(row=1, column=1).font = Font(bold=True, size=14)
    sheet.merge_cells('A1:J1')

    # Headers
    headers = [
        "Name", "Wochenstunden", "Soll (Jahr)", "Ist (Jahr)",
        "Saldo (Jahr)", "Überstunden kum.",
        "Urlaub Budget", "Urlaub genommen", "Urlaub Rest",
        "Krankheitstage"
    ]
    for col_num, header in enumerate(headers, 1):
        cell = sheet.cell(row=3, column=col_num)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCE5FF", end_color="CCE5FF", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    # Data rows
    row = 4
    for user in users:
        # Calculate yearly totals
        yearly_target = Decimal('0')
        yearly_actual = Decimal('0')

        for month in range(1, 13):
            target = calculation_service.get_monthly_target(db, user, year, month)
            actual = calculation_service.get_monthly_actual(db, user, year, month)
            yearly_target += target
            yearly_actual += actual

        yearly_balance = yearly_actual - yearly_target
        overtime = calculation_service.get_overtime_account(db, user, year, 12)

        # Vacation account
        vacation_account = calculation_service.get_vacation_account(db, user, year)

        # Sick days
        daily_target = calculation_service.get_daily_target(user)
        if daily_target == 0:
            daily_target = Decimal('8.0')

        sick_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.SICK,
            extract('year', Absence.date) == year
        ).all()
        sick_hours = sum(float(a.hours) for a in sick_absences)
        sick_days = sick_hours / float(daily_target)

        # Write data
        sheet.cell(row=row, column=1).value = f"{user.last_name}, {user.first_name}"
        sheet.cell(row=row, column=2).value = float(user.weekly_hours)
        sheet.cell(row=row, column=3).value = float(yearly_target)
        sheet.cell(row=row, column=3).number_format = '0.00'
        sheet.cell(row=row, column=4).value = float(yearly_actual)
        sheet.cell(row=row, column=4).number_format = '0.00'
        sheet.cell(row=row, column=5).value = float(yearly_balance)
        sheet.cell(row=row, column=5).number_format = '0.00'

        # Color code balance
        if yearly_balance > 0:
            sheet.cell(row=row, column=5).font = Font(color="006400")
        elif yearly_balance < 0:
            sheet.cell(row=row, column=5).font = Font(color="8B0000")

        sheet.cell(row=row, column=6).value = float(overtime)
        sheet.cell(row=row, column=6).number_format = '0.00'

        if overtime > 0:
            sheet.cell(row=row, column=6).font = Font(color="006400")
        elif overtime < 0:
            sheet.cell(row=row, column=6).font = Font(color="8B0000")

        sheet.cell(row=row, column=7).value = vacation_account['budget_days']
        sheet.cell(row=row, column=8).value = float(vacation_account['used_days'])
        sheet.cell(row=row, column=8).number_format = '0.0'
        sheet.cell(row=row, column=9).value = float(vacation_account['remaining_days'])
        sheet.cell(row=row, column=9).number_format = '0.0'
        sheet.cell(row=row, column=10).value = sick_days
        sheet.cell(row=row, column=10).number_format = '0.0'

        row += 1

    # Adjust column widths
    for col in range(1, 11):
        sheet.column_dimensions[get_column_letter(col)].width = 14


def _create_absences_overview_sheet(wb: Workbook, db: Session, users: List[User], year: int):
    """Create absences overview sheet."""
    sheet = wb.create_sheet(title="Abwesenheiten")

    # Title
    sheet.cell(row=1, column=1).value = f"Abwesenheiten {year}"
    sheet.cell(row=1, column=1).font = Font(bold=True, size=14)
    sheet.merge_cells('A1:F1')

    # Headers
    headers = ["Name", "Urlaub (Tage)", "Krank (Tage)", "Fortbildung (Tage)", "Sonstiges (Tage)", "Gesamt (Tage)"]
    for col_num, header in enumerate(headers, 1):
        cell = sheet.cell(row=3, column=col_num)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCE5FF", end_color="CCE5FF", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    # Data rows
    row = 4
    for user in users:
        daily_target = calculation_service.get_daily_target(user)
        if daily_target == 0:
            daily_target = Decimal('8.0')

        # Calculate days for each absence type
        vacation_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.VACATION,
            extract('year', Absence.date) == year
        ).all()
        vacation_hours = sum(float(a.hours) for a in vacation_absences)
        vacation_days = vacation_hours / float(daily_target)

        sick_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.SICK,
            extract('year', Absence.date) == year
        ).all()
        sick_hours = sum(float(a.hours) for a in sick_absences)
        sick_days = sick_hours / float(daily_target)

        training_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.TRAINING,
            extract('year', Absence.date) == year
        ).all()
        training_hours = sum(float(a.hours) for a in training_absences)
        training_days = training_hours / float(daily_target)

        other_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.OTHER,
            extract('year', Absence.date) == year
        ).all()
        other_hours = sum(float(a.hours) for a in other_absences)
        other_days = other_hours / float(daily_target)

        total_days = vacation_days + sick_days + training_days + other_days

        # Write data
        sheet.cell(row=row, column=1).value = f"{user.last_name}, {user.first_name}"
        sheet.cell(row=row, column=2).value = vacation_days
        sheet.cell(row=row, column=2).number_format = '0.0'
        sheet.cell(row=row, column=3).value = sick_days
        sheet.cell(row=row, column=3).number_format = '0.0'
        sheet.cell(row=row, column=4).value = training_days
        sheet.cell(row=row, column=4).number_format = '0.0'
        sheet.cell(row=row, column=5).value = other_days
        sheet.cell(row=row, column=5).number_format = '0.0'
        sheet.cell(row=row, column=6).value = total_days
        sheet.cell(row=row, column=6).number_format = '0.0'
        sheet.cell(row=row, column=6).font = Font(bold=True)

        row += 1

    # Adjust column widths
    for col in range(1, 7):
        sheet.column_dimensions[get_column_letter(col)].width = 16


def _create_employee_yearly_sheet(wb: Workbook, db: Session, user: User, year: int):
    """
    Create detailed yearly sheet for a single employee with all days.
    Similar to monthly report but for the entire year.
    """
    sheet = wb.create_sheet(title=f"{user.last_name[:20]}")

    # Title
    sheet.cell(row=1, column=1).value = f"{user.first_name} {user.last_name} - Jahresreport {year}"
    sheet.cell(row=1, column=1).font = Font(bold=True, size=14)
    sheet.merge_cells('A1:J1')

    # Row 2: ArbZG-relevante Mitarbeiter-Flags (§16 ArbZG Aufzeichnungspflicht)
    sheet.cell(row=2, column=1).value = "§18 ArbZG-befreit:"
    sheet.cell(row=2, column=1).font = Font(bold=True)
    sheet.cell(row=2, column=2).value = "Ja" if user.exempt_from_arbzg else "Nein"
    sheet.cell(row=2, column=4).value = "Nachtarbeitnehmer (§6 Abs. 2 ArbZG):"
    sheet.cell(row=2, column=4).font = Font(bold=True)
    sheet.cell(row=2, column=5).value = "Ja" if user.is_night_worker else "Nein"

    # Row 3: Column headers
    headers = ["Datum", "Wochentag", "Von", "Bis", "Pause (Min)", "Netto (Std)", "Soll (Std)", "Differenz", "Abwesenheit", "Bemerkung"]
    for col_num, header in enumerate(headers, 1):
        cell = sheet.cell(row=3, column=col_num)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCE5FF", end_color="CCE5FF", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    # Get all time entries for the year
    time_entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        extract('year', TimeEntry.date) == year
    ).all()
    entries_by_date = {entry.date: entry for entry in time_entries}

    # Get all absences for the year
    absences = db.query(Absence).filter(
        Absence.user_id == user.id,
        extract('year', Absence.date) == year
    ).all()
    absences_by_date = {absence.date: absence for absence in absences}

    # Get public holidays for the year
    holidays = db.query(PublicHoliday).filter(
        PublicHoliday.year == year
    ).all()
    holidays_by_date = {holiday.date: holiday for holiday in holidays}

    # German weekday names
    weekday_names = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

    row = 4
    total_net = Decimal('0.00')
    total_target = Decimal('0.00')
    night_work_count = 0
    current_month = 0

    # Iterate through all days of the year
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    current_date = start_date

    while current_date <= end_date:
        # Add month separator
        if current_date.month != current_month:
            if current_month > 0:
                row += 1  # Empty row between months

            current_month = current_date.month
            month_names = [
                "Januar", "Februar", "März", "April", "Mai", "Juni",
                "Juli", "August", "September", "Oktober", "November", "Dezember"
            ]

            sheet.cell(row=row, column=1).value = month_names[current_month - 1]
            sheet.cell(row=row, column=1).font = Font(bold=True, size=12)
            sheet.cell(row=row, column=1).fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            sheet.merge_cells(f'A{row}:J{row}')
            row += 1

        weekday = current_date.weekday()
        weekday_name = weekday_names[weekday]
        is_sunday = weekday == 6

        is_weekend = weekday >= 5
        is_holiday = current_date in holidays_by_date
        absence = absences_by_date.get(current_date)

        sheet.cell(row=row, column=1).value = current_date
        sheet.cell(row=row, column=1).number_format = 'DD.MM.YYYY'
        sheet.cell(row=row, column=2).value = weekday_name

        entry = entries_by_date.get(current_date)

        # Night work check (§6 / §2 Abs. 4 ArbZG)
        is_night_wrk = (entry is not None and entry.end_time is not None
                        and _is_night_work_export(entry.start_time, entry.end_time))
        if is_night_wrk:
            night_work_count += 1

        if entry:
            sheet.cell(row=row, column=3).value = entry.start_time.strftime('%H:%M')
            sheet.cell(row=row, column=4).value = entry.end_time.strftime('%H:%M') if entry.end_time else 'offen'
            sheet.cell(row=row, column=5).value = entry.break_minutes
            sheet.cell(row=row, column=6).value = float(entry.net_hours)
            sheet.cell(row=row, column=6).number_format = '0.00'
            # Bemerkung (col 10): §10-Ausnahmegrund hat Vorrang, dann entry.note
            bemerkung_parts = []
            if entry.sunday_exception_reason and (is_sunday or is_holiday):
                bemerkung_parts.append(f"§10-Ausnahmegrund: {entry.sunday_exception_reason}")
            if entry.note:
                bemerkung_parts.append(entry.note)
            if bemerkung_parts:
                sheet.cell(row=row, column=10).value = " | ".join(bemerkung_parts)
            net = entry.net_hours
            total_net += net
        else:
            net = Decimal('0.00')
            sheet.cell(row=row, column=6).value = 0.00
            sheet.cell(row=row, column=6).number_format = '0.00'

        weekly_hours = calculation_service.get_weekly_hours_for_date(db, user, current_date)
        daily_target = calculation_service.get_daily_target(user, weekly_hours)

        # Target hours + Abwesenheit (col 9) – korrekte Labels für §9/§10/§6
        if is_weekend:
            target = Decimal('0.00')
            if is_sunday and entry:
                abw = "Sonntagsarbeit (§9/§10 ArbZG)"
            elif is_sunday:
                abw = "Sonntag"
            else:
                abw = "Samstag"
            if is_night_wrk:
                abw += " | Nachtarbeit (§6 ArbZG)"
            sheet.cell(row=row, column=9).value = abw
            for col in range(1, 11):
                sheet.cell(row=row, column=col).fill = PatternFill(start_color="E8E8E8", end_color="E8E8E8", fill_type="solid")
        elif is_holiday:
            target = Decimal('0.00')
            holiday = holidays_by_date[current_date]
            if entry:
                abw = f"Feiertagsarbeit: {holiday.name} (§9/§10 ArbZG)"
            else:
                abw = f"Feiertag: {holiday.name}"
            if is_night_wrk:
                abw += " | Nachtarbeit (§6 ArbZG)"
            sheet.cell(row=row, column=9).value = abw
            for col in range(1, 11):
                sheet.cell(row=row, column=col).fill = PatternFill(start_color="FFFFCC", end_color="FFFFCC", fill_type="solid")
        elif absence:
            target = Decimal('0.00')
            absence_type_map = {
                "vacation": "Urlaub",
                "sick": "Krank",
                "training": "Fortbildung",
                "other": "Sonstiges"
            }
            type_name = absence_type_map.get(absence.type.value, absence.type.value)
            sheet.cell(row=row, column=9).value = f"{type_name} ({float(absence.hours)}h)"
            if absence.note:
                sheet.cell(row=row, column=10).value = absence.note
        else:
            target = daily_target
            if is_night_wrk:
                sheet.cell(row=row, column=9).value = "Nachtarbeit (§6 ArbZG)"

        sheet.cell(row=row, column=7).value = float(target)
        sheet.cell(row=row, column=7).number_format = '0.00'
        total_target += target

        diff = net - target
        sheet.cell(row=row, column=8).value = float(diff)
        sheet.cell(row=row, column=8).number_format = '0.00'

        if diff > 0:
            sheet.cell(row=row, column=8).font = Font(color="006400")
        elif diff < 0:
            sheet.cell(row=row, column=8).font = Font(color="8B0000")

        row += 1
        current_date += timedelta(days=1)

    # Summary section
    row += 2
    sheet.cell(row=row, column=1).value = "Jahressumme"
    sheet.cell(row=row, column=1).font = Font(bold=True, size=12)

    row += 1
    sheet.cell(row=row, column=1).value = "Soll-Stunden Jahr:"
    sheet.cell(row=row, column=2).value = float(total_target)
    sheet.cell(row=row, column=2).number_format = '0.00'
    sheet.cell(row=row, column=1).font = Font(bold=True)

    row += 1
    sheet.cell(row=row, column=1).value = "Ist-Stunden Jahr:"
    sheet.cell(row=row, column=2).value = float(total_net)
    sheet.cell(row=row, column=2).number_format = '0.00'
    sheet.cell(row=row, column=1).font = Font(bold=True)

    row += 1
    yearly_balance = total_net - total_target
    sheet.cell(row=row, column=1).value = "Saldo Jahr:"
    sheet.cell(row=row, column=2).value = float(yearly_balance)
    sheet.cell(row=row, column=2).number_format = '0.00'
    sheet.cell(row=row, column=1).font = Font(bold=True)
    if yearly_balance > 0:
        sheet.cell(row=row, column=2).font = Font(bold=True, color="006400")
    elif yearly_balance < 0:
        sheet.cell(row=row, column=2).font = Font(bold=True, color="8B0000")

    row += 1
    overtime_account = calculation_service.get_overtime_account(db, user, year, 12)
    sheet.cell(row=row, column=1).value = "Überstunden kumuliert:"
    sheet.cell(row=row, column=2).value = float(overtime_account)
    sheet.cell(row=row, column=2).number_format = '0.00'
    sheet.cell(row=row, column=1).font = Font(bold=True)
    if overtime_account > 0:
        sheet.cell(row=row, column=2).font = Font(bold=True, color="006400")
    elif overtime_account < 0:
        sheet.cell(row=row, column=2).font = Font(bold=True, color="8B0000")

    row += 1
    vacation_account = calculation_service.get_vacation_account(db, user, year)
    sheet.cell(row=row, column=1).value = "Urlaub genommen (Tage):"
    sheet.cell(row=row, column=2).value = float(vacation_account['used_days'])
    sheet.cell(row=row, column=2).number_format = '0.0'

    row += 1
    sheet.cell(row=row, column=1).value = "Urlaub Rest (Tage):"
    sheet.cell(row=row, column=2).value = float(vacation_account['remaining_days'])
    sheet.cell(row=row, column=2).number_format = '0.0'

    row += 1
    sheet.cell(row=row, column=1).value = "Nachtarbeitstage (§6 ArbZG):"
    sheet.cell(row=row, column=2).value = night_work_count
    sheet.cell(row=row, column=1).font = Font(bold=True)

    # Adjust column widths
    sheet.column_dimensions['A'].width = 12
    sheet.column_dimensions['B'].width = 10
    sheet.column_dimensions['C'].width = 8
    sheet.column_dimensions['D'].width = 8
    sheet.column_dimensions['E'].width = 12
    sheet.column_dimensions['F'].width = 12
    sheet.column_dimensions['G'].width = 12
    sheet.column_dimensions['H'].width = 10
    sheet.column_dimensions['I'].width = 28
    sheet.column_dimensions['J'].width = 35


def generate_yearly_report_classic(db: Session, year: int) -> BytesIO:
    """
    Generate classic yearly report (compact format with months as columns).
    Creates one sheet per employee.

    Args:
        db: Database session
        year: Year

    Returns:
        BytesIO object containing Excel file
    """
    wb = Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Get all active employees
    users = db.query(User).filter(User.is_active == True).order_by(User.last_name, User.first_name).all()

    for user in users:
        _create_employee_classic_sheet(wb, db, user, year)

    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output


def _create_employee_classic_sheet(wb: Workbook, db: Session, user: User, year: int):
    """
    Create classic yearly overview sheet for one employee.
    Format: Months as columns, compact overview with running balances.
    """
    sheet = wb.create_sheet(title=f"{user.last_name}")

    # Styles
    header_font = Font(bold=True, size=11)
    bold_font = Font(bold=True, size=10)
    normal_font = Font(size=10)
    center_align = Alignment(horizontal='center', vertical='center')
    right_align = Alignment(horizontal='right', vertical='center')

    # Month names
    month_names = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
                   'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

    # Row 1: Practice header
    sheet.cell(row=1, column=1).value = "Praxis Dr. Klotz-Rödig"
    sheet.cell(row=1, column=1).font = header_font
    sheet.cell(row=1, column=2).value = "Möhlestraße 11"
    sheet.cell(row=1, column=4).value = "85354"
    sheet.cell(row=1, column=5).value = "Freising"

    # Row 2: Employee name
    sheet.cell(row=2, column=1).value = "Mitarbeiterin"
    sheet.cell(row=2, column=1).font = bold_font
    sheet.cell(row=2, column=2).value = f"{user.first_name} {user.last_name}"

    # Row 3: Year title + ArbZG-Flags
    sheet.cell(row=3, column=1).value = "Jahresarbeitszeiten"
    sheet.cell(row=3, column=1).font = bold_font
    sheet.cell(row=3, column=2).value = year
    sheet.cell(row=3, column=15).value = "§18 ArbZG-befreit:"
    sheet.cell(row=3, column=15).font = bold_font
    sheet.cell(row=3, column=16).value = "Ja" if user.exempt_from_arbzg else "Nein"
    sheet.cell(row=2, column=15).value = "Nachtarbeitnehmer (§6 Abs. 2):"
    sheet.cell(row=2, column=15).font = bold_font
    sheet.cell(row=2, column=16).value = "Ja" if user.is_night_worker else "Nein"

    # Row 4: Month headers (columns 3-14 for Jan-Dec)
    sheet.cell(row=4, column=2).value = "Übertrag"
    sheet.cell(row=4, column=2).font = bold_font
    sheet.cell(row=4, column=2).alignment = center_align
    for i, month_name in enumerate(month_names, start=3):
        sheet.cell(row=4, column=i).value = month_name
        sheet.cell(row=4, column=i).font = bold_font
        sheet.cell(row=4, column=i).alignment = center_align

    # Row 5: Previous year carry-over
    sheet.cell(row=5, column=2).value = "Vorjahr"
    sheet.cell(row=5, column=2).font = normal_font

    # Get previous year overtime
    prev_year_overtime = calculation_service.get_overtime_account(db, user, year - 1, 12)
    sheet.cell(row=5, column=3).value = float(prev_year_overtime)
    sheet.cell(row=5, column=3).number_format = '0.0'

    # Row labels
    sheet.cell(row=6, column=1).value = "Zahl Arbeitstage im Monat"
    sheet.cell(row=7, column=1).value = "Sollstunden im Monat"
    sheet.cell(row=8, column=1).value = "minus Krank  Std."
    sheet.cell(row=9, column=1).value = "minus Urlaub  Std."
    sheet.cell(row=10, column=1).value = "aktuelle Sollstundenzahl"
    sheet.cell(row=11, column=1).value = "erbrachte Stunden"
    sheet.cell(row=12, column=1).value = "StundenSaldo"
    sheet.cell(row=13, column=1).value = "Jan.- Monatsende"
    sheet.cell(row=14, column=1).value = "Überstunden / Minusstunden"
    sheet.cell(row=15, column=1).value = "Resturlaub + Urlaub in Std."
    sheet.cell(row=16, column=1).value = "Nachtarbeitstage (§6 ArbZG)"

    for row in range(6, 17):
        sheet.cell(row=row, column=1).font = normal_font

    # Calculate data for each month
    for month in range(1, 13):
        col = month + 2  # Column 3 = January, ..., Column 14 = December

        # Row 6: Working days in month
        working_days = calculation_service.get_working_days_in_month(db, year, month)
        sheet.cell(row=6, column=col).value = working_days
        sheet.cell(row=6, column=col).alignment = center_align

        # Row 7: Target hours
        target_hours = calculation_service.get_monthly_target(db, user, year, month)
        sheet.cell(row=7, column=col).value = float(target_hours)
        sheet.cell(row=7, column=col).number_format = '0.0'
        sheet.cell(row=7, column=col).alignment = right_align

        # Row 8: Sick hours
        sick_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.SICK,
            extract('year', Absence.date) == year,
            extract('month', Absence.date) == month
        ).all()
        sick_hours = sum(float(a.hours) for a in sick_absences)
        sheet.cell(row=8, column=col).value = sick_hours
        sheet.cell(row=8, column=col).number_format = '0.0'
        sheet.cell(row=8, column=col).alignment = right_align

        # Row 9: Vacation hours
        vacation_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.VACATION,
            extract('year', Absence.date) == year,
            extract('month', Absence.date) == month
        ).all()
        vacation_hours = sum(float(a.hours) for a in vacation_absences)
        sheet.cell(row=9, column=col).value = vacation_hours
        sheet.cell(row=9, column=col).number_format = '0.0'
        sheet.cell(row=9, column=col).alignment = right_align

        # Row 10: Adjusted target (Target - Sick - Vacation)
        adjusted_target = float(target_hours) - sick_hours - vacation_hours
        sheet.cell(row=10, column=col).value = adjusted_target
        sheet.cell(row=10, column=col).number_format = '0.0'
        sheet.cell(row=10, column=col).alignment = right_align

        # Row 11: Actual hours
        actual_hours = calculation_service.get_monthly_actual(db, user, year, month)
        sheet.cell(row=11, column=col).value = float(actual_hours)
        sheet.cell(row=11, column=col).number_format = '0.0'
        sheet.cell(row=11, column=col).alignment = right_align

        # Row 12: Monthly balance (Actual - Adjusted Target)
        monthly_balance = float(actual_hours) - adjusted_target
        sheet.cell(row=12, column=col).value = monthly_balance
        sheet.cell(row=12, column=col).number_format = '0.0'
        sheet.cell(row=12, column=col).alignment = right_align

        # Apply color coding to balance
        if monthly_balance > 0:
            sheet.cell(row=12, column=col).fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
        elif monthly_balance < 0:
            sheet.cell(row=12, column=col).fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')

        # Row 14: Cumulative overtime
        cumulative_overtime = calculation_service.get_overtime_account(db, user, year, month)
        sheet.cell(row=14, column=col).value = float(cumulative_overtime)
        sheet.cell(row=14, column=col).number_format = '0.0'
        sheet.cell(row=14, column=col).alignment = right_align
        sheet.cell(row=14, column=col).font = bold_font

        # Apply color coding to cumulative
        if cumulative_overtime > 0:
            sheet.cell(row=14, column=col).fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
        elif cumulative_overtime < 0:
            sheet.cell(row=14, column=col).fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')

        # Row 15: Remaining vacation in hours
        vacation_account = calculation_service.get_vacation_account(db, user, year)
        # Calculate remaining vacation up to this month
        vacation_used_ytd = sum(
            float(a.hours) for a in db.query(Absence).filter(
                Absence.user_id == user.id,
                Absence.type == AbsenceType.VACATION,
                extract('year', Absence.date) == year,
                extract('month', Absence.date) <= month
            ).all()
        )
        vacation_remaining = float(vacation_account['budget_hours']) - vacation_used_ytd
        sheet.cell(row=15, column=col).value = vacation_remaining
        sheet.cell(row=15, column=col).number_format = '0.0'
        sheet.cell(row=15, column=col).alignment = right_align

        # Row 16: Night work days per month (§6 ArbZG)
        month_entries = db.query(TimeEntry).filter(
            TimeEntry.user_id == user.id,
            extract('year', TimeEntry.date) == year,
            extract('month', TimeEntry.date) == month,
            TimeEntry.end_time.isnot(None),
        ).all()
        night_days = sum(
            1 for e in month_entries
            if _is_night_work_export(e.start_time, e.end_time)
        )
        sheet.cell(row=16, column=col).value = night_days
        sheet.cell(row=16, column=col).alignment = center_align

    # Add daily hours info in corner (like in original)
    sheet.cell(row=6, column=17).value = "tägl. Std:"
    sheet.cell(row=6, column=17).font = normal_font
    daily_hours = calculation_service.get_daily_target(user)
    sheet.cell(row=6, column=18).value = float(daily_hours)
    sheet.cell(row=6, column=18).number_format = '0.0'

    # Set column widths
    sheet.column_dimensions['A'].width = 28
    sheet.column_dimensions['B'].width = 12
    for col in range(3, 15):
        sheet.column_dimensions[get_column_letter(col)].width = 11
    sheet.column_dimensions['Q'].width = 10
    sheet.column_dimensions['R'].width = 8

    # Add borders to data area
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    for row in range(4, 17):
        for col in range(2, 15):
            sheet.cell(row=row, column=col).border = thin_border
