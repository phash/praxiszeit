from io import BytesIO
from datetime import date, datetime
from calendar import monthrange
from decimal import Decimal
from typing import List
from sqlalchemy.orm import Session
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from app.models import User, TimeEntry, Absence, PublicHoliday
from app.services import calculation_service
from sqlalchemy import extract


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

    # Header row
    headers = ["Datum", "Wochentag", "Von", "Bis", "Pause (Min)", "Netto (Std)", "Soll (Std)", "Differenz", "Abwesenheit", "Bemerkung"]
    for col_num, header in enumerate(headers, 1):
        cell = sheet.cell(row=1, column=col_num)
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

    row = 2
    total_net = Decimal('0.00')
    total_target = Decimal('0.00')

    # Iterate through all days of the month
    for day in range(1, last_day + 1):
        current_date = date(year, month, day)
        weekday = current_date.weekday()
        weekday_name = weekday_names[weekday]

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

        if entry:
            # Time entry exists
            sheet.cell(row=row, column=3).value = entry.start_time.strftime('%H:%M')
            sheet.cell(row=row, column=4).value = entry.end_time.strftime('%H:%M')
            sheet.cell(row=row, column=5).value = entry.break_minutes
            sheet.cell(row=row, column=6).value = float(entry.net_hours)
            sheet.cell(row=row, column=6).number_format = '0.00'
            if entry.note:
                sheet.cell(row=row, column=10).value = entry.note

            net = entry.net_hours
            total_net += net
        else:
            # No time entry
            net = Decimal('0.00')
            sheet.cell(row=row, column=6).value = 0.00
            sheet.cell(row=row, column=6).number_format = '0.00'

        # Target hours
        if is_weekend:
            target = Decimal('0.00')
            sheet.cell(row=row, column=9).value = "Wochenende"
            # Gray background for weekend
            for col in range(1, 11):
                sheet.cell(row=row, column=col).fill = PatternFill(start_color="E8E8E8", end_color="E8E8E8", fill_type="solid")
        elif is_holiday:
            target = Decimal('0.00')
            holiday = holidays_by_date[current_date]
            sheet.cell(row=row, column=9).value = f"Feiertag"
            sheet.cell(row=row, column=10).value = holiday.name
            # Yellow background for holiday
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
            # Regular working day
            target = daily_target

        sheet.cell(row=row, column=7).value = float(target)
        sheet.cell(row=row, column=7).number_format = '0.00'
        total_target += target

        # Difference
        diff = net - target
        sheet.cell(row=row, column=8).value = float(diff)
        sheet.cell(row=row, column=8).number_format = '0.00'

        # Color code difference
        if diff > 0:
            sheet.cell(row=row, column=8).font = Font(color="006400")  # Dark green
        elif diff < 0:
            sheet.cell(row=row, column=8).font = Font(color="8B0000")  # Dark red

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

    # Adjust column widths
    sheet.column_dimensions['A'].width = 12
    sheet.column_dimensions['B'].width = 10
    sheet.column_dimensions['C'].width = 8
    sheet.column_dimensions['D'].width = 8
    sheet.column_dimensions['E'].width = 12
    sheet.column_dimensions['F'].width = 12
    sheet.column_dimensions['G'].width = 12
    sheet.column_dimensions['H'].width = 10
    sheet.column_dimensions['I'].width = 20
    sheet.column_dimensions['J'].width = 30
