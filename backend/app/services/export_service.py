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
from app.services.arbzg_utils import is_night_work
from app.config import settings
from sqlalchemy import extract


def generate_monthly_report(db: Session, year: int, month: int, include_health_data: bool = False) -> BytesIO:
    """
    Generate Excel report for all employees for a given month.
    Creates one sheet per employee.

    Args:
        db: Database session
        year: Year
        month: Month (1-12)
        include_health_data: If False (default), sick absences are shown as "Abwesenheit" (Art. 9 DSGVO protection)

    Returns:
        BytesIO object containing Excel file
    """
    wb = Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Get all active, non-hidden employees
    users = db.query(User).filter(User.is_active == True, User.is_hidden == False).order_by(User.last_name, User.first_name).all()

    for user in users:
        _create_employee_sheet(wb, db, user, year, month, include_health_data)

    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output


def _create_employee_sheet(wb: Workbook, db: Session, user: User, year: int, month: int, include_health_data: bool = False):
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

    # Get all time entries for the month (list-based: multiple entries per day)
    time_entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        extract('year', TimeEntry.date) == year,
        extract('month', TimeEntry.date) == month
    ).order_by(TimeEntry.start_time).all()
    entries_by_date: dict = {}
    for entry in time_entries:
        entries_by_date.setdefault(entry.date, []).append(entry)

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

        # Get time entries if exist (may be multiple per day)
        day_entries = entries_by_date.get(current_date, [])

        # Night work check (§6 / §2 Abs. 4 ArbZG)
        is_night_wrk = any(
            e.end_time is not None and is_night_work(e.start_time, e.end_time)
            for e in day_entries
        )
        if is_night_wrk:
            night_work_count += 1

        if day_entries:
            first_start = day_entries[0].start_time
            last_end = day_entries[-1].end_time
            total_break = sum(e.break_minutes or 0 for e in day_entries)
            total_day_net = sum(e.net_hours for e in day_entries)
            sheet.cell(row=row, column=3).value = first_start.strftime('%H:%M')
            sheet.cell(row=row, column=4).value = last_end.strftime('%H:%M') if last_end else 'offen'
            sheet.cell(row=row, column=5).value = total_break
            sheet.cell(row=row, column=6).value = float(total_day_net)
            sheet.cell(row=row, column=6).number_format = '0.00'
            # Bemerkung (col 10): §10-Ausnahmegrund hat Vorrang, dann entry.note
            bemerkung_parts = []
            for e in day_entries:
                if e.sunday_exception_reason and (is_sunday or is_holiday):
                    bemerkung_parts.append(f"§10-Ausnahmegrund: {e.sunday_exception_reason}")
                if e.note:
                    bemerkung_parts.append(e.note)
            if bemerkung_parts:
                sheet.cell(row=row, column=10).value = " | ".join(bemerkung_parts)
            net = total_day_net
            total_net += net
        else:
            net = Decimal('0.00')
            sheet.cell(row=row, column=6).value = 0.00
            sheet.cell(row=row, column=6).number_format = '0.00'

        # Per-day target using historical weekly hours
        weekly_hours = calculation_service.get_weekly_hours_for_date(db, user, current_date)
        daily_target = calculation_service.get_daily_target_for_date(user, current_date, weekly_hours=weekly_hours)

        # Target hours + Abwesenheit (col 9) – korrekte Labels für §9/§10/§6
        if is_weekend:
            target = Decimal('0.00')
            if is_sunday and day_entries:
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
            if day_entries:
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
            # DSGVO F-003: mask sick absences when health data export not explicitly requested
            if absence.type.value == "sick" and not include_health_data:
                type_name = "Abwesenheit"
                # Do not expose sick note (may contain diagnosis details)
            else:
                absence_type_map = {
                    "vacation": "Urlaub",
                    "sick": "Krank",
                    "training": "Fortbildung",
                    "overtime": "Überstundenausgleich",
                    "other": "Sonstiges"
                }
                type_name = absence_type_map.get(absence.type.value, absence.type.value)
                if absence.note:
                    sheet.cell(row=row, column=10).value = absence.note
            sheet.cell(row=row, column=9).value = f"{type_name} ({float(absence.hours)}h)"
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


def generate_yearly_report(db: Session, year: int, include_health_data: bool = False) -> BytesIO:
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

    # Get all active, non-hidden employees
    users = db.query(User).filter(User.is_active == True, User.is_hidden == False).order_by(User.last_name, User.first_name).all()

    # Create overview sheet
    _create_yearly_overview_sheet(wb, db, users, year, include_health_data)

    # Create absences overview sheet
    _create_absences_overview_sheet(wb, db, users, year, include_health_data)

    # Create employee detail sheets
    for user in users:
        _create_employee_yearly_sheet(wb, db, user, year, include_health_data)

    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output


def _create_yearly_overview_sheet(wb: Workbook, db: Session, users: List[User], year: int, include_health_data: bool = False):
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

        # Sick days (uses current daily target for hours-to-days conversion — approximate)
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
        if include_health_data:
            sheet.cell(row=row, column=10).value = sick_days
            sheet.cell(row=row, column=10).number_format = '0.0'
        else:
            sheet.cell(row=row, column=10).value = "–"

        row += 1

    if not include_health_data:
        # Mark the column header to indicate data is protected
        sheet.cell(row=3, column=10).value = "Krankheitstage (geschützt)"

    # Adjust column widths
    for col in range(1, 11):
        sheet.column_dimensions[get_column_letter(col)].width = 14


def _create_absences_overview_sheet(wb: Workbook, db: Session, users: List[User], year: int, include_health_data: bool = False):
    """Create absences overview sheet."""
    sheet = wb.create_sheet(title="Abwesenheiten")

    # Title
    sheet.cell(row=1, column=1).value = f"Abwesenheiten {year}"
    sheet.cell(row=1, column=1).font = Font(bold=True, size=14)
    sheet.merge_cells('A1:G1')

    # Headers
    headers = ["Name", "Urlaub (Tage)", "Krank (Tage)", "Fortbildung (Tage)", "ÜStd.-Ausgleich (Tage)", "Sonstiges (Tage)", "Gesamt (Tage)"]
    for col_num, header in enumerate(headers, 1):
        cell = sheet.cell(row=3, column=col_num)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCE5FF", end_color="CCE5FF", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    # Data rows
    row = 4
    for user in users:
        # Uses current daily target for hours-to-days conversion — approximate for display
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

        overtime_comp_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.OVERTIME,
            extract('year', Absence.date) == year
        ).all()
        overtime_comp_hours = sum(float(a.hours) for a in overtime_comp_absences)
        overtime_comp_days = overtime_comp_hours / float(daily_target)

        other_absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            Absence.type == AbsenceType.OTHER,
            extract('year', Absence.date) == year
        ).all()
        other_hours = sum(float(a.hours) for a in other_absences)
        other_days = other_hours / float(daily_target)

        total_days = vacation_days + (sick_days if include_health_data else 0) + training_days + overtime_comp_days + other_days

        # Write data
        sheet.cell(row=row, column=1).value = f"{user.last_name}, {user.first_name}"
        sheet.cell(row=row, column=2).value = vacation_days
        sheet.cell(row=row, column=2).number_format = '0.0'
        if include_health_data:
            sheet.cell(row=row, column=3).value = sick_days
            sheet.cell(row=row, column=3).number_format = '0.0'
        else:
            sheet.cell(row=row, column=3).value = "–"
        sheet.cell(row=row, column=4).value = training_days
        sheet.cell(row=row, column=4).number_format = '0.0'
        sheet.cell(row=row, column=5).value = overtime_comp_days
        sheet.cell(row=row, column=5).number_format = '0.0'
        sheet.cell(row=row, column=6).value = other_days
        sheet.cell(row=row, column=6).number_format = '0.0'
        sheet.cell(row=row, column=7).value = total_days
        sheet.cell(row=row, column=7).number_format = '0.0'
        sheet.cell(row=row, column=7).font = Font(bold=True)

        row += 1

    if not include_health_data:
        sheet.cell(row=3, column=3).value = "Krank (Tage) (geschützt)"

    # Adjust column widths
    for col in range(1, 8):
        sheet.column_dimensions[get_column_letter(col)].width = 16


def _create_employee_yearly_sheet(wb: Workbook, db: Session, user: User, year: int, include_health_data: bool = False):
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
    # DSGVO F-006: is_night_worker is health-adjacent data – only show when include_health_data=True
    sheet.cell(row=2, column=4).value = "Nachtarbeitnehmer (§6 Abs. 2 ArbZG):"
    sheet.cell(row=2, column=4).font = Font(bold=True)
    sheet.cell(row=2, column=5).value = ("Ja" if user.is_night_worker else "Nein") if include_health_data else "–"

    # Row 3: Column headers
    headers = ["Datum", "Wochentag", "Von", "Bis", "Pause (Min)", "Netto (Std)", "Soll (Std)", "Differenz", "Abwesenheit", "Bemerkung"]
    for col_num, header in enumerate(headers, 1):
        cell = sheet.cell(row=3, column=col_num)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCE5FF", end_color="CCE5FF", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    # Get all time entries for the year (list-based: multiple entries per day)
    time_entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        extract('year', TimeEntry.date) == year
    ).order_by(TimeEntry.start_time).all()
    entries_by_date: dict = {}
    for entry in time_entries:
        entries_by_date.setdefault(entry.date, []).append(entry)

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

        day_entries = entries_by_date.get(current_date, [])

        # Night work check (§6 / §2 Abs. 4 ArbZG)
        is_night_wrk = any(
            e.end_time is not None and is_night_work(e.start_time, e.end_time)
            for e in day_entries
        )
        if is_night_wrk:
            night_work_count += 1

        if day_entries:
            first_start = day_entries[0].start_time
            last_end = day_entries[-1].end_time
            total_break = sum(e.break_minutes or 0 for e in day_entries)
            total_day_net = sum(e.net_hours for e in day_entries)
            sheet.cell(row=row, column=3).value = first_start.strftime('%H:%M')
            sheet.cell(row=row, column=4).value = last_end.strftime('%H:%M') if last_end else 'offen'
            sheet.cell(row=row, column=5).value = total_break
            sheet.cell(row=row, column=6).value = float(total_day_net)
            sheet.cell(row=row, column=6).number_format = '0.00'
            # Bemerkung (col 10): §10-Ausnahmegrund hat Vorrang, dann entry.note
            bemerkung_parts = []
            for e in day_entries:
                if e.sunday_exception_reason and (is_sunday or is_holiday):
                    bemerkung_parts.append(f"§10-Ausnahmegrund: {e.sunday_exception_reason}")
                if e.note:
                    bemerkung_parts.append(e.note)
            if bemerkung_parts:
                sheet.cell(row=row, column=10).value = " | ".join(bemerkung_parts)
            net = total_day_net
            total_net += net
        else:
            net = Decimal('0.00')
            sheet.cell(row=row, column=6).value = 0.00
            sheet.cell(row=row, column=6).number_format = '0.00'

        weekly_hours = calculation_service.get_weekly_hours_for_date(db, user, current_date)
        daily_target = calculation_service.get_daily_target_for_date(user, current_date, weekly_hours=weekly_hours)

        # Target hours + Abwesenheit (col 9) – korrekte Labels für §9/§10/§6
        if is_weekend:
            target = Decimal('0.00')
            if is_sunday and day_entries:
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
            if day_entries:
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
            # DSGVO F-003: mask sick absences unless health data explicitly requested
            if absence.type.value == "sick" and not include_health_data:
                type_name = "Abwesenheit"
            else:
                absence_type_map = {
                    "vacation": "Urlaub",
                    "sick": "Krank",
                    "training": "Fortbildung",
                    "overtime": "Überstundenausgleich",
                    "other": "Sonstiges"
                }
                type_name = absence_type_map.get(absence.type.value, absence.type.value)
                if absence.note:
                    sheet.cell(row=row, column=10).value = absence.note
            sheet.cell(row=row, column=9).value = f"{type_name} ({float(absence.hours)}h)"
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


def generate_yearly_report_classic(db: Session, year: int, include_health_data: bool = False) -> BytesIO:
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

    # Get all active, non-hidden employees
    users = db.query(User).filter(User.is_active == True, User.is_hidden == False).order_by(User.last_name, User.first_name).all()

    for user in users:
        _create_employee_classic_sheet(wb, db, user, year, include_health_data)

    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output


def _create_employee_classic_sheet(wb: Workbook, db: Session, user: User, year: int, include_health_data: bool = False):
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

    # Row 1: Practice header (DSGVO F-016: use configurable env vars)
    sheet.cell(row=1, column=1).value = settings.PRACTICE_NAME
    sheet.cell(row=1, column=1).font = header_font
    if settings.PRACTICE_ADDRESS:
        sheet.cell(row=1, column=2).value = settings.PRACTICE_ADDRESS

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
    # DSGVO F-006: protect health-adjacent is_night_worker
    sheet.cell(row=2, column=15).value = "Nachtarbeitnehmer (§6 Abs. 2):"
    sheet.cell(row=2, column=15).font = bold_font
    sheet.cell(row=2, column=16).value = ("Ja" if user.is_night_worker else "Nein") if include_health_data else "–"

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
        if include_health_data:
            sheet.cell(row=8, column=col).value = sick_hours
            sheet.cell(row=8, column=col).number_format = '0.0'
        else:
            sheet.cell(row=8, column=col).value = "–"
            sick_hours = 0  # Treat as 0 for subsequent calculations
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
        night_days = len({e.date for e in month_entries if is_night_work(e.start_time, e.end_time)})
        sheet.cell(row=16, column=col).value = night_days
        sheet.cell(row=16, column=col).alignment = center_align

    # Add daily hours info in corner (current value — informational)
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


# ---------------------------------------------------------------------------
# PDF Export (reportlab)
# ---------------------------------------------------------------------------

def generate_monthly_report_pdf(db: Session, year: int, month: int, include_health_data: bool = False) -> BytesIO:
    """
    Generate PDF monthly report for all employees.
    One page per employee, landscape A4.
    Same data as Excel monthly report.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=15 * mm, leftMargin=15 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"PraxisZeit Monatsreport {month:02d}/{year}",
    )

    # Styles
    s_normal = ParagraphStyle('n', fontName='Helvetica', fontSize=7, leading=9)
    s_bold = ParagraphStyle('b', fontName='Helvetica-Bold', fontSize=7, leading=9)
    s_center = ParagraphStyle('c', fontName='Helvetica', fontSize=7, leading=9, alignment=TA_CENTER)
    s_title = ParagraphStyle('t', fontName='Helvetica-Bold', fontSize=10, leading=13)
    s_sum_lbl = ParagraphStyle('sl', fontName='Helvetica-Bold', fontSize=7.5, leading=10)
    s_sum_val = ParagraphStyle('sv', fontName='Helvetica', fontSize=7.5, leading=10)

    def colored(text, hex_color, bold=False):
        fn = 'Helvetica-Bold' if bold else 'Helvetica'
        return Paragraph(text, ParagraphStyle('col', fontName=fn, fontSize=7, leading=9,
                                              textColor=colors.HexColor(hex_color)))

    month_names = ['Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni',
                   'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

    users = (db.query(User)
             .filter(User.is_active == True, User.is_hidden == False)
             .order_by(User.last_name, User.first_name)
             .all())

    # Landscape A4: 297mm − 30mm margins = 267mm usable
    col_widths = [22*mm, 10*mm, 13*mm, 13*mm, 15*mm, 16*mm, 14*mm, 16*mm, 74*mm, 74*mm]
    weekday_names = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    absence_type_map = {"vacation": "Urlaub", "sick": "Krank", "training": "Fortbildung", "overtime": "Überstundenausgleich", "other": "Sonstiges"}

    story = []

    for i, user in enumerate(users):
        if i > 0:
            story.append(PageBreak())

        # ── Title ──
        story.append(Paragraph(
            f"PraxisZeit \u2013 Monatsreport {month_names[month - 1]} {year}",
            s_title
        ))
        story.append(Spacer(1, 2 * mm))

        # ── Employee meta ──
        arbzg_flag = " | \u00a718-befreit" if user.exempt_from_arbzg else ""
        night_flag = " | Nachtarbeitnehmer (\u00a76)" if user.is_night_worker else ""
        meta_label = f"{user.first_name} {user.last_name}  \u2013  {float(user.weekly_hours):.1f}h/Woche{arbzg_flag}{night_flag}"
        story.append(Paragraph(meta_label, ParagraphStyle('meta', fontName='Helvetica', fontSize=8, leading=10,
                                                           textColor=colors.HexColor('#374151'))))
        story.append(Spacer(1, 2 * mm))

        # ── Fetch data ──
        _, last_day = monthrange(year, month)

        time_entries = db.query(TimeEntry).filter(
            TimeEntry.user_id == user.id,
            extract('year', TimeEntry.date) == year,
            extract('month', TimeEntry.date) == month,
        ).order_by(TimeEntry.start_time).all()
        entries_by_date: dict = {}
        for te in time_entries:
            entries_by_date.setdefault(te.date, []).append(te)

        absences = db.query(Absence).filter(
            Absence.user_id == user.id,
            extract('year', Absence.date) == year,
            extract('month', Absence.date) == month,
        ).all()
        absences_by_date = {a.date: a for a in absences}

        holidays = db.query(PublicHoliday).filter(
            extract('year', PublicHoliday.date) == year,
            extract('month', PublicHoliday.date) == month,
        ).all()
        holidays_by_date = {h.date: h for h in holidays}

        # ── Build table ──
        headers = ['Datum', 'WT', 'Von', 'Bis', 'Pause\n(Min)', 'Netto\n(Std)', 'Soll\n(Std)', 'Diff.', 'Abwesenheit', 'Bemerkung']
        table_data = [[Paragraph(h, ParagraphStyle('hdr', fontName='Helvetica-Bold', fontSize=7,
                                                    leading=9, alignment=TA_CENTER))
                       for h in headers]]
        row_bgs = {}  # row_index -> HexColor

        total_net = Decimal('0.00')
        total_target = Decimal('0.00')
        night_work_count = 0

        for day in range(1, last_day + 1):
            cur = date(year, month, day)
            wd = cur.weekday()
            is_weekend = wd >= 5
            is_sunday = wd == 6
            is_holiday = cur in holidays_by_date
            absence = absences_by_date.get(cur)
            day_entries = entries_by_date.get(cur, [])

            is_night = any(
                e.end_time is not None and is_night_work(e.start_time, e.end_time)
                for e in day_entries
            )
            if is_night:
                night_work_count += 1

            if day_entries:
                von = day_entries[0].start_time.strftime('%H:%M')
                last_end = day_entries[-1].end_time
                bis = last_end.strftime('%H:%M') if last_end else 'offen'
                pause_str = str(sum(e.break_minutes or 0 for e in day_entries))
                total_day_net = sum(e.net_hours for e in day_entries)
                netto_val = float(total_day_net)
                net = total_day_net
                total_net += net
                bem_parts = []
                for e in day_entries:
                    if e.sunday_exception_reason and (is_sunday or is_holiday):
                        bem_parts.append(f"\u00a710: {e.sunday_exception_reason}")
                    if e.note:
                        bem_parts.append(e.note)
                bem = " | ".join(bem_parts)
            else:
                von = bis = pause_str = bem = ''
                netto_val = 0.0
                net = Decimal('0.00')

            # Per-day target using historical weekly hours
            weekly_h = calculation_service.get_weekly_hours_for_date(db, user, cur)
            daily_target = calculation_service.get_daily_target_for_date(user, cur, weekly_hours=weekly_h)

            if is_weekend:
                target = Decimal('0.00')
                if is_sunday and day_entries:
                    abw = 'Sonntagsarbeit (\u00a79/\u00a710)'
                elif is_sunday:
                    abw = 'Sonntag'
                else:
                    abw = 'Samstag'
                if is_night:
                    abw += ' | Nachtarbeit'
                bg = colors.HexColor('#E8E8E8')
            elif is_holiday:
                target = Decimal('0.00')
                hname = holidays_by_date[cur].name
                abw = f"Feiertagsarbeit: {hname}" if day_entries else f"Feiertag: {hname}"
                if is_night:
                    abw += ' | Nachtarbeit'
                bg = colors.HexColor('#FFFFCC')
            elif absence:
                target = Decimal('0.00')
                if absence.type.value == 'sick' and not include_health_data:
                    type_name = 'Abwesenheit'
                    bem = ''
                else:
                    type_name = absence_type_map.get(absence.type.value, absence.type.value)
                    if absence.note:
                        if absence.type == AbsenceType.SICK and not include_health_data:
                            pass  # Don't show sick notes without health data permission
                        else:
                            bem = absence.note
                abw = f"{type_name} ({float(absence.hours):.1f}h)"
                bg = None
            else:
                target = daily_target
                abw = 'Nachtarbeit (\u00a76 ArbZG)' if is_night else ''
                bg = None

            total_target += target
            diff = net - target
            diff_str = f"{float(diff):+.2f}"
            if diff > 0:
                diff_cell = colored(diff_str, '#006400', bold=True)
            elif diff < 0:
                diff_cell = colored(diff_str, '#8B0000', bold=True)
            else:
                diff_cell = Paragraph(diff_str, s_center)

            row = [
                Paragraph(cur.strftime('%d.%m.%Y'), s_normal),
                Paragraph(weekday_names[wd], s_center),
                Paragraph(von, s_center),
                Paragraph(bis, s_center),
                Paragraph(pause_str, s_center),
                Paragraph(f"{netto_val:.2f}", s_center),
                Paragraph(f"{float(target):.2f}", s_center),
                diff_cell,
                Paragraph(abw, s_normal),
                Paragraph(bem, s_normal),
            ]
            table_data.append(row)
            if bg:
                row_bgs[len(table_data) - 1] = bg

        tbl_style = [
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#CCE5FF')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#CCCCCC')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ]
        for row_idx, bg_color in row_bgs.items():
            tbl_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), bg_color))

        main_tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        main_tbl.setStyle(TableStyle(tbl_style))
        story.append(main_tbl)

        # ── Summary ──
        story.append(Spacer(1, 4 * mm))
        monthly_balance = total_net - total_target
        overtime_account = calculation_service.get_overtime_account(db, user, year, month)
        vacation_account = calculation_service.get_vacation_account(db, user, year)

        bal_color = '#006400' if monthly_balance > 0 else ('#8B0000' if monthly_balance < 0 else '#1e293b')
        ot_color = '#006400' if overtime_account > 0 else ('#8B0000' if overtime_account < 0 else '#1e293b')

        summary_rows = [
            [Paragraph('Zusammenfassung', ParagraphStyle('st', fontName='Helvetica-Bold', fontSize=8, leading=10)), ''],
            [Paragraph('Soll-Stunden:', s_sum_lbl), Paragraph(f"{float(total_target):.2f} h", s_sum_val)],
            [Paragraph('Ist-Stunden:', s_sum_lbl), Paragraph(f"{float(total_net):.2f} h", s_sum_val)],
            [Paragraph('Saldo Monat:', s_sum_lbl),
             Paragraph(f"{float(monthly_balance):+.2f} h",
                       ParagraphStyle('sb', fontName='Helvetica-Bold', fontSize=7.5,
                                      textColor=colors.HexColor(bal_color)))],
            [Paragraph('\u00dcberstunden kumuliert:', s_sum_lbl),
             Paragraph(f"{float(overtime_account):+.2f} h",
                       ParagraphStyle('so', fontName='Helvetica-Bold', fontSize=7.5,
                                      textColor=colors.HexColor(ot_color)))],
            [Paragraph('Urlaub genommen:', s_sum_lbl),
             Paragraph(f"{float(vacation_account['used_hours']):.2f} h", s_sum_val)],
            [Paragraph('Urlaub Rest:', s_sum_lbl),
             Paragraph(f"{float(vacation_account['remaining_hours']):.2f} h", s_sum_val)],
            [Paragraph('Nachtarbeitstage (\u00a76 ArbZG):', s_sum_lbl),
             Paragraph(str(night_work_count), s_sum_val)],
        ]
        sum_tbl = Table(summary_rows, colWidths=[55 * mm, 35 * mm])
        sum_tbl.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#CCE5FF')),
            ('SPAN', (0, 0), (1, 0)),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#CCCCCC')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8FAFC')),
        ]))
        story.append(sum_tbl)

    doc.build(story)
    output.seek(0)
    return output
