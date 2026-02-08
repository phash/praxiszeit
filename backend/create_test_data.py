"""
Create test data for 4 employees with complete time entries for 2026.
"""
import sys
import os
from datetime import date, datetime, timedelta
from decimal import Decimal
import random

# Add app to path
sys.path.insert(0, '/app')

from app.database import SessionLocal
from app.models import User, TimeEntry, Absence, PublicHoliday, AbsenceType, WorkingHoursChange
from app.services import auth_service
import uuid


def create_test_employees():
    """Create 4 test employees with different working hours."""
    db = SessionLocal()

    employees = [
        {
            "email": "anna.mueller@praxis.de",
            "first_name": "Anna",
            "last_name": "Müller",
            "weekly_hours": Decimal("40.0"),  # Vollzeit
            "vacation_days": 30,
            "calendar_color": "#93C5FD",
            "track_hours": True
        },
        {
            "email": "sophie.schmidt@praxis.de",
            "first_name": "Sophie",
            "last_name": "Schmidt",
            "weekly_hours": Decimal("20.0"),  # Teilzeit
            "vacation_days": 15,
            "calendar_color": "#F9A8D4",
            "track_hours": True
        },
        {
            "email": "lisa.wagner@praxis.de",
            "first_name": "Lisa",
            "last_name": "Wagner",
            "weekly_hours": Decimal("38.5"),  # Vollzeit
            "vacation_days": 30,
            "calendar_color": "#86EFAC",
            "track_hours": True
        },
        {
            "email": "julia.weber@praxis.de",
            "first_name": "Julia",
            "last_name": "Weber",
            "weekly_hours": Decimal("10.0"),  # Teilzeit (Mini)
            "vacation_days": 8,
            "calendar_color": "#FDBA74",
            "track_hours": True
        }
    ]

    created_users = []

    for emp_data in employees:
        # Check if user already exists
        existing = db.query(User).filter(User.email == emp_data["email"]).first()
        if existing:
            print(f"✓ User {emp_data['email']} already exists")
            created_users.append(existing)
            continue

        # Create user
        user = User(
            email=emp_data["email"],
            first_name=emp_data["first_name"],
            last_name=emp_data["last_name"],
            password_hash=auth_service.hash_password("test123"),
            weekly_hours=emp_data["weekly_hours"],
            vacation_days=emp_data["vacation_days"],
            calendar_color=emp_data["calendar_color"],
            track_hours=emp_data["track_hours"],
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        created_users.append(user)
        print(f"✓ Created user: {user.first_name} {user.last_name} ({user.weekly_hours}h/week)")

    db.close()
    return created_users


def get_holidays_for_2026():
    """Get all public holidays for 2026."""
    db = SessionLocal()
    holidays = db.query(PublicHoliday).filter(PublicHoliday.year == 2026).all()
    holiday_dates = {h.date for h in holidays}
    db.close()
    return holiday_dates


def create_absences(user, db, holiday_dates):
    """Create realistic absences for a user."""
    absences_to_create = []

    # Calculate how many vacation days based on weekly hours
    vacation_budget = user.vacation_days
    daily_hours = float(user.weekly_hours) / 5

    # Vacation periods (realistic dates)
    vacation_periods = [
        (date(2026, 1, 5), date(2026, 1, 9)),    # Early January
        (date(2026, 4, 6), date(2026, 4, 17)),   # Easter holidays (2 weeks)
        (date(2026, 7, 20), date(2026, 7, 31)),  # Summer vacation
        (date(2026, 12, 23), date(2026, 12, 31)) # Christmas/New Year
    ]

    # Take some vacation days
    vacation_days_taken = 0
    for start, end in vacation_periods:
        if vacation_days_taken >= vacation_budget * 0.8:  # Use up to 80% of budget
            break

        current = start
        while current <= end and vacation_days_taken < vacation_budget * 0.8:
            # Only weekdays, not holidays
            if current.weekday() < 5 and current not in holiday_dates:
                absences_to_create.append({
                    "user_id": user.id,
                    "date": current,
                    "end_date": end,
                    "type": AbsenceType.VACATION,
                    "hours": Decimal(str(daily_hours)),
                    "note": "Urlaub"
                })
                vacation_days_taken += 1
            current += timedelta(days=1)

    # Sick days (2-4 random days)
    sick_count = random.randint(2, 4)
    sick_dates = []

    # Avoid vacation periods
    vacation_date_set = set()
    for start, end in vacation_periods:
        current = start
        while current <= end:
            vacation_date_set.add(current)
            current += timedelta(days=1)

    attempts = 0
    while len(sick_dates) < sick_count and attempts < 100:
        attempts += 1
        # Random date in 2026
        day_of_year = random.randint(1, 365)
        sick_date = date(2026, 1, 1) + timedelta(days=day_of_year - 1)

        # Must be weekday, not holiday, not vacation, not duplicate
        if (sick_date.weekday() < 5 and
            sick_date not in holiday_dates and
            sick_date not in vacation_date_set and
            sick_date not in sick_dates):
            sick_dates.append(sick_date)

    for sick_date in sick_dates:
        absences_to_create.append({
            "user_id": user.id,
            "date": sick_date,
            "end_date": None,
            "type": AbsenceType.SICK,
            "hours": Decimal(str(daily_hours)),
            "note": "Krankheit"
        })

    # Training (1-2 days)
    training_count = random.randint(1, 2)
    training_dates = [
        date(2026, 3, 15),  # March
        date(2026, 9, 10),  # September
    ][:training_count]

    for training_date in training_dates:
        if training_date.weekday() < 5 and training_date not in holiday_dates:
            absences_to_create.append({
                "user_id": user.id,
                "date": training_date,
                "end_date": None,
                "type": AbsenceType.TRAINING,
                "hours": Decimal(str(daily_hours)),
                "note": "Fortbildung"
            })

    # Create all absences
    for abs_data in absences_to_create:
        absence = Absence(**abs_data)
        db.add(absence)

    db.commit()
    print(f"  ✓ Created {len(absences_to_create)} absences ({vacation_days_taken} vacation days)")

    return {a["date"] for a in absences_to_create}


def create_time_entries(user, db, holiday_dates, absence_dates):
    """Create time entries for all working days in 2026."""
    daily_hours = float(user.weekly_hours) / 5

    # Start from January 1, 2026
    current_date = date(2026, 1, 1)
    end_date = date(2026, 12, 31)

    entries_created = 0

    while current_date <= end_date:
        # Only create entries for weekdays
        if current_date.weekday() < 5:  # Monday to Friday
            # Skip holidays and absences
            if current_date not in holiday_dates and current_date not in absence_dates:
                # Generate realistic times
                # Start time: 7:00 - 9:00
                start_hour = random.randint(7, 9)
                start_minute = random.choice([0, 15, 30, 45])
                start_time = datetime.combine(current_date, datetime.min.time()).replace(
                    hour=start_hour, minute=start_minute
                )

                # Add some variation to daily hours (±10%)
                target_hours = daily_hours * random.uniform(0.9, 1.1)

                # Lunch break: 30-60 minutes
                break_minutes = random.choice([30, 45, 60])

                # Calculate end time
                total_minutes = int(target_hours * 60) + break_minutes
                end_time = start_time + timedelta(minutes=total_minutes)

                # Create entry (net_hours is calculated automatically)
                entry = TimeEntry(
                    user_id=user.id,
                    date=current_date,
                    start_time=start_time.time(),
                    end_time=end_time.time(),
                    break_minutes=break_minutes,
                    note=""
                )
                db.add(entry)
                entries_created += 1

        current_date += timedelta(days=1)

    db.commit()
    print(f"  ✓ Created {entries_created} time entries")


def add_hours_changes():
    """Add historical working hours changes for some employees."""
    db = SessionLocal()

    # Sophie Schmidt: Changed from 30h to 20h on March 1st
    sophie = db.query(User).filter(User.email == "sophie.schmidt@praxis.de").first()
    if sophie:
        # Check if change already exists
        existing = db.query(WorkingHoursChange).filter(
            WorkingHoursChange.user_id == sophie.id,
            WorkingHoursChange.effective_from == date(2026, 3, 1)
        ).first()

        if not existing:
            change = WorkingHoursChange(
                user_id=sophie.id,
                effective_from=date(2026, 3, 1),
                weekly_hours=Decimal("20.0"),
                note="Reduzierung von 30h auf 20h wegen Kinderbetreuung"
            )
            db.add(change)

            # Also update historical entries for Jan-Feb to 30h (6h/day instead of 4h/day)
            jan_feb_entries = db.query(TimeEntry).filter(
                TimeEntry.user_id == sophie.id,
                TimeEntry.date < date(2026, 3, 1)
            ).all()

            for entry in jan_feb_entries:
                # Recalculate with 6h/day (30h/week) instead of 4h/day
                target_hours = 6.0 * random.uniform(0.9, 1.1)
                total_minutes = int(target_hours * 60) + entry.break_minutes

                # Convert time to datetime, add minutes, then back to time
                start_dt = datetime.combine(entry.date, entry.start_time)
                end_dt = start_dt + timedelta(minutes=total_minutes)
                entry.end_time = end_dt.time()

            db.commit()
            print(f"✓ Added working hours change for Sophie (30h → 20h on 01.03.2026)")
            print(f"  Updated {len(jan_feb_entries)} entries for Jan-Feb to 30h/week")

    db.close()


def main():
    """Main function to create all test data."""
    print("=" * 60)
    print("Creating Test Data for 2026")
    print("=" * 60)

    # Create employees
    print("\n1. Creating employees...")
    users = create_test_employees()

    # Get holidays
    print("\n2. Loading holidays...")
    holiday_dates = get_holidays_for_2026()
    print(f"  ✓ Loaded {len(holiday_dates)} holidays")

    # Create data for each employee
    print("\n3. Creating absences and time entries...")
    db = SessionLocal()

    # Get user IDs
    user_ids = [u.id for u in users]

    # Reload users in the new session
    users = db.query(User).filter(User.id.in_(user_ids)).all()

    for user in users:
        print(f"\n{user.first_name} {user.last_name} ({user.weekly_hours}h/week):")

        # Delete existing data
        db.query(Absence).filter(Absence.user_id == user.id).delete()
        db.query(TimeEntry).filter(TimeEntry.user_id == user.id).delete()
        db.commit()

        # Create absences
        absence_dates = create_absences(user, db, holiday_dates)

        # Create time entries
        create_time_entries(user, db, holiday_dates, absence_dates)

    db.close()

    # Add working hours changes
    print("\n4. Adding working hours changes...")
    add_hours_changes()

    print("\n" + "=" * 60)
    print("✓ Test data creation completed!")
    print("=" * 60)
    print("\nTest users created:")
    print("- anna.mueller@praxis.de (40h/week, Vollzeit)")
    print("- sophie.schmidt@praxis.de (20h/week, Teilzeit, war 30h bis Feb)")
    print("- lisa.wagner@praxis.de (38.5h/week, Vollzeit)")
    print("- julia.weber@praxis.de (10h/week, Teilzeit Mini)")
    print("\nAll passwords: test123")
    print("=" * 60)


if __name__ == "__main__":
    main()
