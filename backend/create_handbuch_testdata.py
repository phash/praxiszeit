"""
Erstellt realistische Testdaten für Handbuch-Screenshots.
1 Admin + 5 Mitarbeiter (Voll- und Teilzeit), ~2 Monate Daten (Jan+Feb 2026).
"""
import sys
import os
from datetime import date, datetime, timedelta, time as dt_time
from decimal import Decimal
import random

sys.path.insert(0, '/app')

from app.database import SessionLocal
from app.models import (
    User, TimeEntry, Absence, PublicHoliday, AbsenceType,
    WorkingHoursChange, ChangeRequest
)
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.models.user import UserRole
from app.services import auth_service

random.seed(42)  # Reproduzierbar

# ── Mitarbeiter-Definitionen ──────────────────────────────────────────────────
EMPLOYEES = [
    {
        "username": "maria.hoffmann",
        "email": "maria.hoffmann@praxis.de",
        "first_name": "Maria",
        "last_name": "Hoffmann",
        "weekly_hours": Decimal("40.0"),   # Vollzeit
        "work_days_per_week": 5,
        "vacation_days": 30,
        "calendar_color": "#93C5FD",       # Blau
        "track_hours": True,
        "is_night_worker": False,
        "exempt_from_arbzg": False,
    },
    {
        "username": "thomas.bauer",
        "email": "thomas.bauer@praxis.de",
        "first_name": "Thomas",
        "last_name": "Bauer",
        "weekly_hours": Decimal("38.5"),   # Vollzeit (Tarifvertrag)
        "work_days_per_week": 5,
        "vacation_days": 28,
        "calendar_color": "#86EFAC",       # Grün
        "track_hours": True,
        "is_night_worker": False,
        "exempt_from_arbzg": False,
    },
    {
        "username": "sarah.klein",
        "email": "sarah.klein@praxis.de",
        "first_name": "Sarah",
        "last_name": "Klein",
        "weekly_hours": Decimal("25.0"),   # Teilzeit
        "work_days_per_week": 5,
        "vacation_days": 20,
        "calendar_color": "#F9A8D4",       # Rosa
        "track_hours": True,
        "is_night_worker": False,
        "exempt_from_arbzg": False,
    },
    {
        "username": "petra.schulz",
        "email": "petra.schulz@praxis.de",
        "first_name": "Petra",
        "last_name": "Schulz",
        "weekly_hours": Decimal("20.0"),   # Teilzeit
        "work_days_per_week": 4,
        "vacation_days": 16,
        "calendar_color": "#FDBA74",       # Orange
        "track_hours": True,
        "is_night_worker": False,
        "exempt_from_arbzg": False,
    },
    {
        "username": "julia.meyer",
        "email": "julia.meyer@praxis.de",
        "first_name": "Julia",
        "last_name": "Meyer",
        "weekly_hours": Decimal("10.0"),   # Minijob
        "work_days_per_week": 2,
        "vacation_days": 8,
        "calendar_color": "#C4B5FD",       # Lila
        "track_hours": True,
        "is_night_worker": False,
        "exempt_from_arbzg": False,
    },
]

# ── Datum-Bereich ─────────────────────────────────────────────────────────────
START_DATE = date(2026, 1, 5)   # Erster Arbeitstag (Mo nach Neujahr)
END_DATE   = date(2026, 2, 27)  # Gestern (Fr)


def get_holiday_dates(db) -> set:
    holidays = db.query(PublicHoliday).filter(
        PublicHoliday.date >= START_DATE,
        PublicHoliday.date <= END_DATE
    ).all()
    return {h.date for h in holidays}


def create_employees(db) -> list:
    created = []
    for emp in EMPLOYEES:
        existing = db.query(User).filter(User.username == emp["username"]).first()
        if existing:
            print(f"  ~ {emp['first_name']} {emp['last_name']} existiert bereits (übersprungen)")
            created.append(existing)
            continue

        u = User(
            username=emp["username"],
            email=emp["email"],
            first_name=emp["first_name"],
            last_name=emp["last_name"],
            password_hash=auth_service.hash_password("Mitarbeiter2026!"),
            role=UserRole.EMPLOYEE,
            weekly_hours=emp["weekly_hours"],
            work_days_per_week=emp["work_days_per_week"],
            vacation_days=emp["vacation_days"],
            calendar_color=emp["calendar_color"],
            track_hours=emp["track_hours"],
            is_night_worker=emp["is_night_worker"],
            exempt_from_arbzg=emp["exempt_from_arbzg"],
            is_active=True,
            is_hidden=False,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        created.append(u)
        print(f"  ✓ {emp['first_name']} {emp['last_name']} ({emp['weekly_hours']}h/Woche) angelegt")
    return created


def working_days_in_range(start: date, end: date, holiday_dates: set,
                           work_days_per_week: int = 5) -> list:
    """Gibt alle Arbeitstage zurück, ggf. mit Ausnahme von Freitagen (bei 4-Tage-Woche)."""
    days = []
    current = start
    while current <= end:
        wd = current.weekday()  # 0=Mo, 4=Fr, 5=Sa, 6=So
        is_workday = wd < 5     # Mo–Fr
        if work_days_per_week == 4:
            is_workday = wd < 4  # Mo–Do
        elif work_days_per_week == 2:
            is_workday = wd in (1, 3)  # Di und Do
        if is_workday and current not in holiday_dates:
            days.append(current)
        current += timedelta(days=1)
    return days


def make_time_entry(user: User, d: date, target_hours: float,
                    variation: float = 0.08) -> TimeEntry:
    """Erzeugt einen realistischen Zeitstempel für einen Tag."""
    # Startzeit: 7:00–9:00
    start_h = random.randint(7, 9)
    start_m = random.choice([0, 15, 30, 45])
    start = dt_time(start_h, start_m)

    # Variation auf Soll-Stunden
    actual_hours = target_hours * random.uniform(1 - variation, 1 + variation)
    actual_hours = round(actual_hours * 4) / 4  # auf 15-Min runden

    # Pause: 30 oder 45 Minuten (abhängig von Stundenanzahl)
    break_min = 45 if actual_hours >= 6.5 else 30
    total_min = int(actual_hours * 60) + break_min

    start_dt = datetime.combine(d, start)
    end_dt = start_dt + timedelta(minutes=total_min)

    return TimeEntry(
        user_id=user.id,
        date=d,
        start_time=start,
        end_time=end_dt.time(),
        break_minutes=break_min,
        note="",
    )


def create_time_entries_for_user(db, user: User, holiday_dates: set):
    daily_hours = float(user.weekly_hours) / user.work_days_per_week

    # Abwesenheiten dieses Nutzers abrufen
    absence_dates = {
        a.date for a in db.query(Absence).filter(Absence.user_id == user.id).all()
    }

    work_days = working_days_in_range(START_DATE, END_DATE, holiday_dates,
                                      user.work_days_per_week)

    count = 0
    for d in work_days:
        if d in absence_dates:
            continue
        entry = make_time_entry(user, d, daily_hours)
        db.add(entry)
        count += 1

    db.commit()
    print(f"    ✓ {count} Zeiteinträge erstellt")


def create_absences_for_user(db, user: User, holiday_dates: set):
    """Erstellt realistische Abwesenheiten je nach Mitarbeiter."""
    absence_entries = []
    username = user.username
    daily_h = Decimal(str(round(float(user.weekly_hours) / user.work_days_per_week, 2)))

    def add_absence(d, end_d, absence_type, note_text):
        absence_entries.append(Absence(
            user_id=user.id, date=d, end_date=end_d,
            type=absence_type, hours=daily_h, note=note_text,
        ))

    if username == "maria.hoffmann":
        # Urlaub: letzte Januarwoche (26.–30. Jan)
        vac_start, vac_end = date(2026, 1, 26), date(2026, 1, 30)
        d = vac_start
        while d <= vac_end:
            if d.weekday() < 5 and d not in holiday_dates:
                add_absence(d, vac_end, AbsenceType.VACATION, "Kurzurlaub")
            d += timedelta(days=1)
        # Krank: 3.–4. Feb
        for sick_day in [date(2026, 2, 3), date(2026, 2, 4)]:
            add_absence(sick_day, None, AbsenceType.SICK, "Erkältung")

    elif username == "thomas.bauer":
        # Fortbildung: 13. Jan
        add_absence(date(2026, 1, 13), None, AbsenceType.TRAINING, "Erste-Hilfe-Kurs")
        # Urlaub: 16.–20. Feb
        vac_start, vac_end = date(2026, 2, 16), date(2026, 2, 20)
        d = vac_start
        while d <= vac_end:
            if d.weekday() < 5 and d not in holiday_dates:
                add_absence(d, vac_end, AbsenceType.VACATION, "Winterurlaub")
            d += timedelta(days=1)

    elif username == "sarah.klein":
        # Krank: 20.–22. Jan (3 Tage)
        for sick_day in [date(2026, 1, 20), date(2026, 1, 21), date(2026, 1, 22)]:
            add_absence(sick_day, None, AbsenceType.SICK, "Grippe")

    elif username == "petra.schulz":
        # Urlaub: 5.–7. Feb (Mo–Mi; sie hat 4-Tage-Woche Mo–Do)
        vac_start, vac_end = date(2026, 2, 5), date(2026, 2, 7)
        d = vac_start
        while d <= vac_end:
            if d.weekday() < 4 and d not in holiday_dates:
                add_absence(d, vac_end, AbsenceType.VACATION, "Brückentag")
            d += timedelta(days=1)

    elif username == "julia.meyer":
        # Sonstiges: 27. Jan
        add_absence(date(2026, 1, 27), None, AbsenceType.OTHER, "Arzttermin")

    for a in absence_entries:
        db.add(a)
    db.commit()
    print(f"    ✓ {len(absence_entries)} Abwesenheiten erstellt")


def _insert_change_request(db, user_id, time_entry_id, req_type, status,
                            orig_start, orig_end, orig_break,
                            prop_start, prop_end, prop_break,
                            reason, rejection_reason=None):
    """Insert a change request via direct psycopg2 to bypass SQLAlchemy enum issues."""
    conn = db.connection()
    raw_conn = conn.connection
    cursor = raw_conn.cursor()
    cursor.execute(f"""
        INSERT INTO change_requests (
            id, user_id, request_type, status, time_entry_id,
            original_start_time, original_end_time, original_break_minutes,
            proposed_start_time, proposed_end_time, proposed_break_minutes,
            reason, rejection_reason
        ) VALUES (
            gen_random_uuid(), %s,
            %s::changerequesttype, %s::changerequeststatus,
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """, (
        str(user_id), req_type, status, str(time_entry_id),
        str(orig_start), str(orig_end), orig_break,
        str(prop_start), str(prop_end), prop_break,
        reason, rejection_reason,
    ))
    raw_conn.commit()


def create_change_requests(db, users: list):
    """Erstellt einige Change Requests (Korrekturanträge)."""
    maria = next((u for u in users if u.username == "maria.hoffmann"), None)
    thomas = next((u for u in users if u.username == "thomas.bauer"), None)

    count = 0
    if maria:
        entry = db.query(TimeEntry).filter(
            TimeEntry.user_id == maria.id,
            TimeEntry.date == date(2026, 2, 10)
        ).first()
        if entry:
            _insert_change_request(
                db, maria.id, entry.id, "update", "pending",
                entry.start_time, entry.end_time, entry.break_minutes,
                "08:00:00", "16:45:00", 45,
                "Hatte vergessen, mich einzustempeln – tatsächliche Arbeitszeit war 8:00–16:45 Uhr.",
            )
            count += 1

    if thomas:
        entry = db.query(TimeEntry).filter(
            TimeEntry.user_id == thomas.id,
            TimeEntry.date == date(2026, 1, 15)
        ).first()
        if entry:
            _insert_change_request(
                db, thomas.id, entry.id, "update", "rejected",
                entry.start_time, entry.end_time, entry.break_minutes,
                "07:30:00", "17:00:00", 30,
                "Bitte Korrektur: hatte durchgehend gearbeitet ohne längere Pause.",
                "Pausen-Nachweis fehlt. Gemäß ArbZG §4 sind bei >6h Arbeitszeit 30 Min. Pause vorgeschrieben.",
            )
            count += 1

    db.commit()
    print(f"  ✓ {count} Change Requests erstellt")


def update_admin_password(db):
    """Setzt Admin-Passwort auf einen sicheren Wert."""
    admin = db.query(User).filter(User.username == "admin").first()
    if admin:
        admin.first_name = "Andreas"
        admin.last_name = "Werner"
        admin.email = "admin@musterpraxis.de"
        admin.password_hash = auth_service.hash_password("Admin2026!")
        db.commit()
        print("  ✓ Admin-Passwort aktualisiert (Admin2026!)")
    else:
        print("  ! Admin-User nicht gefunden")


def main():
    print("=" * 60)
    print("PraxisZeit – Handbuch-Testdaten")
    print(f"Zeitraum: {START_DATE} bis {END_DATE}")
    print("=" * 60)

    db = SessionLocal()
    try:
        # 1. Admin-Daten aktualisieren
        print("\n1. Admin aktualisieren...")
        update_admin_password(db)

        # 2. Feiertage laden
        print("\n2. Feiertage laden...")
        holiday_dates = get_holiday_dates(db)
        print(f"  ✓ {len(holiday_dates)} Feiertage im Zeitraum: {sorted(holiday_dates)}")

        # 3. Mitarbeiter anlegen
        print("\n3. Mitarbeiter anlegen...")
        users = create_employees(db)

        # 4. Bestehende Einträge dieser User löschen
        print("\n4. Alte Einträge bereinigen...")
        for u in users:
            deleted_te = db.query(TimeEntry).filter(TimeEntry.user_id == u.id).delete()
            deleted_ab = db.query(Absence).filter(Absence.user_id == u.id).delete()
            deleted_cr = db.query(ChangeRequest).filter(ChangeRequest.user_id == u.id).delete()
            db.commit()
            if deleted_te or deleted_ab:
                print(f"  ~ {u.first_name}: {deleted_te} Zeiteinträge + {deleted_ab} Abwesenheiten gelöscht")

        # 5. Abwesenheiten + Zeiteinträge pro MA
        print("\n5. Daten pro Mitarbeiter erstellen...")
        for u in users:
            print(f"\n  [{u.first_name} {u.last_name}] {u.weekly_hours}h/Woche, "
                  f"{u.work_days_per_week} Tage/Woche")
            create_absences_for_user(db, u, holiday_dates)
            create_time_entries_for_user(db, u, holiday_dates)

        # 6. Change Requests
        print("\n6. Korrekturanträge erstellen...")
        create_change_requests(db, users)

        print("\n" + "=" * 60)
        print("✅ Testdaten erfolgreich erstellt!")
        print("=" * 60)
        print("\nZugangsdaten:")
        print("  Admin:      admin / Admin2026!")
        print("  Mitarbeiter (alle): Mitarbeiter2026!")
        print("  maria.hoffmann | thomas.bauer | sarah.klein")
        print("  petra.schulz   | julia.meyer")
        print("=" * 60)

    finally:
        db.close()


if __name__ == "__main__":
    main()
