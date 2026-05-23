"""
Testdaten-Setup: Anonymisierung + Testdaten April 2026 – Feb 2027
Ausführen: docker compose exec backend python setup_extended_testdata.py
"""
import sys
import random
from datetime import date, datetime, timedelta, time
from decimal import Decimal

sys.path.insert(0, '/app')

from app.database import SessionLocal, set_superadmin_context
from app.models import (
    User, TimeEntry, Absence, AbsenceType, YearCarryover, PublicHoliday
)
from app.services import calculation_service

TENANT_ID = "00000000-0000-0000-0000-000000000001"

random.seed(42)  # Reproduzierbare Ergebnisse

# ---------------------------------------------------------------------------
# 1. Anonymisierung
# ---------------------------------------------------------------------------

ANON_MAP = {
    # username → (first_name, last_name, email)
    "DEKR":  ("Laura",    "Fischer",    "l.fischer@praxis-demo.de"),
    "DCM":   ("Claudia",  "Mayer",      "c.mayer@praxis-demo.de"),
    "MGB":   ("Gabriele", "Bauer",      "g.bauer@praxis-demo.de"),
    "MMP":   ("Maria",    "Petersen",   "m.petersen@praxis-demo.de"),
    "MCS":   ("Carolin",  "Schmidt",    "c.schmidt@praxis-demo.de"),
    "MMK":   ("Monika",   "Krause",     "m.krause@praxis-demo.de"),
    "MCG":   ("Christine","Günther",    "c.guenther@praxis-demo.de"),
    "manuel":("Manuel",   "Admin",      "admin@praxis-demo.de"),
    "admin": ("Admin",    "Praxis",     "admin2@praxis-demo.de"),
}


def anonymize_users(db):
    print("\n=== Schritt 1: Benutzer anonymisieren ===")
    for username, (fn, ln, email) in ANON_MAP.items():
        user = db.query(User).filter(User.username == username).first()
        if not user:
            continue
        user.first_name = fn
        user.last_name = ln
        user.email = email
        print(f"  ✓ {username}: {fn} {ln} <{email}>")
    db.commit()


# ---------------------------------------------------------------------------
# 2. Hilfsfunktionen
# ---------------------------------------------------------------------------

def get_holiday_dates(db, year):
    holidays = db.query(PublicHoliday).filter(PublicHoliday.year == year).all()
    return {h.date for h in holidays}


def is_workday(d, holiday_dates):
    return d.weekday() < 5 and d not in holiday_dates


def workdays_in_range(start, end, holiday_dates):
    days = []
    cur = start
    while cur <= end:
        if is_workday(cur, holiday_dates):
            days.append(cur)
        cur += timedelta(days=1)
    return days


# ---------------------------------------------------------------------------
# 3. Profildefinitionen (Verhalten pro Mitarbeiter)
# ---------------------------------------------------------------------------

# Jeder Eintrag:
#   daily_variance: Tupel (min_mult, max_mult) relativ zum Tagessoll
#   break_choices: mögliche Pausen in Minuten
#   vacation_remaining: noch zu nehmende Urlaubstage Apr 2026 – Feb 2027
#   sick_days_remaining: noch zu erwartende Krankheitstage
#   training_days: Tage für Fortbildung (absolute Dates)
#   overtime_comp_days: Tage für Überstundenausgleich (absolute Dates)

PROFILES = {
    "DEKR": {   # Chefin 42h – arbeitet immer etwas mehr
        "daily_variance": (1.02, 1.12),
        "break_choices":  [30, 45],
        "start_hour_range": (7, 8),
        "vacation_periods": [
            (date(2026, 5, 4),  date(2026, 5, 8)),    # 1 Woche Mai
            (date(2026, 10, 5), date(2026, 10, 9)),   # 1 Woche Oktober
        ],
        "sick_count":  1,
        "training_dates": [date(2026, 9, 17)],
        "overtime_comp_dates": [],
    },
    "MMP": {    # 30h – Normalläuferin, etwas Überstunden
        "daily_variance": (0.97, 1.07),
        "break_choices":  [30, 45, 60],
        "start_hour_range": (8, 9),
        "vacation_periods": [
            (date(2026, 4, 14), date(2026, 4, 17)),   # Osterferien
            (date(2026, 7, 27), date(2026, 8, 7)),    # Sommerurlaub
            (date(2026, 12, 21), date(2026, 12, 31)), # Jahresende
        ],
        "sick_count": 3,
        "training_dates": [date(2026, 11, 5)],
        "overtime_comp_dates": [date(2026, 6, 26)],
    },
    "MCS": {    # 38.5h – Überstundentyp
        "daily_variance": (1.03, 1.15),
        "break_choices":  [30, 45],
        "start_hour_range": (7, 8),
        "vacation_periods": [
            (date(2026, 6, 1),  date(2026, 6, 5)),    # 1 Woche Juni
            (date(2026, 8, 10), date(2026, 8, 21)),   # 2 Wochen August
        ],
        "sick_count": 2,
        "training_dates": [date(2026, 10, 22), date(2026, 10, 23)],
        "overtime_comp_dates": [date(2026, 5, 15), date(2026, 11, 27)],
    },
    "MMK": {    # 17h Teilzeit – punktgenau, mehr Krankheit
        "daily_variance": (0.95, 1.05),
        "break_choices":  [0, 30],
        "start_hour_range": (8, 9),
        "vacation_periods": [
            (date(2026, 7, 13), date(2026, 7, 24)),   # Sommerurlaub 2 Wochen
        ],
        "sick_count": 5,
        "training_dates": [],
        "overtime_comp_dates": [date(2026, 9, 25)],
    },
    "MGB": {    # 20h Teilzeit – ruhig, wenige Abwesenheiten
        "daily_variance": (0.98, 1.06),
        "break_choices":  [30, 45],
        "start_hour_range": (8, 10),
        "vacation_periods": [
            (date(2026, 5, 25), date(2026, 5, 29)),   # Pfingsten Woche
            (date(2026, 9, 7),  date(2026, 9, 11)),   # September
        ],
        "sick_count": 2,
        "training_dates": [date(2026, 11, 19)],
        "overtime_comp_dates": [],
    },
    "DCM": {    # 31h – Fortbildungen, normaler Alltag
        "daily_variance": (0.96, 1.08),
        "break_choices":  [30, 45, 60],
        "start_hour_range": (8, 9),
        "vacation_periods": [
            (date(2026, 4, 7),  date(2026, 4, 10)),   # Osterferien kurz
            (date(2026, 8, 3),  date(2026, 8, 14)),   # Sommerurlaub
            (date(2026, 12, 27), date(2026, 12, 31)), # Jahresende
        ],
        "sick_count": 3,
        "training_dates": [date(2026, 6, 11), date(2026, 6, 12)],
        "overtime_comp_dates": [date(2026, 10, 16)],
    },
}

# Usernames die 2027 noch Daten bekommen (Jan + Feb)
ACTIVE_USERNAMES = list(PROFILES.keys())


# ---------------------------------------------------------------------------
# 4. Datenbereininung
# ---------------------------------------------------------------------------

def cleanup_future_data(db):
    print("\n=== Schritt 2: Inkonsistente Daten bereinigen ===")

    cutoff = date(2026, 4, 1)  # Ab hier neu generieren

    # Falsche Carryovers löschen
    deleted_co = db.query(YearCarryover).filter(
        YearCarryover.year.in_([2026, 2027])
    ).delete(synchronize_session=False)
    print(f"  ✓ {deleted_co} Carryovers gelöscht (2026/2027 werden neu berechnet)")

    # Abwesenheiten ab April 2026 löschen
    deleted_abs = db.query(Absence).filter(Absence.date >= cutoff).delete(
        synchronize_session=False
    )
    print(f"  ✓ {deleted_abs} Abwesenheiten ab {cutoff} gelöscht")

    db.commit()


# ---------------------------------------------------------------------------
# 5. Abwesenheiten generieren
# ---------------------------------------------------------------------------

def get_already_taken_vacation(db, user_id, year):
    """Zählt bereits gebuchte Urlaubstage vor April im angegebenen Jahr."""
    start = date(year, 1, 1)
    end = date(year, 3, 31)
    abs_list = db.query(Absence).filter(
        Absence.user_id == user_id,
        Absence.type == AbsenceType.VACATION,
        Absence.date >= start,
        Absence.date <= end,
    ).all()
    return len(abs_list)


def create_absences_for_user(db, user, profile, holiday_dates_2026, holiday_dates_2027):
    """Erstellt Abwesenheiten April 2026 – Feb 2027 für einen User."""
    daily_hours = float(user.weekly_hours) / (user.work_days_per_week or 5)
    created = []

    # --- Urlaub 2026 ---
    already_taken = get_already_taken_vacation(db, user.id, 2026)
    budget_2026 = user.vacation_days - already_taken

    for start, end in profile["vacation_periods"]:
        if start.year != 2026:
            continue
        cur = start
        while cur <= end and budget_2026 > 0:
            hd = holiday_dates_2026 if cur.year == 2026 else holiday_dates_2027
            if is_workday(cur, hd):
                abs_ = Absence(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    date=cur,
                    end_date=end,
                    type=AbsenceType.VACATION,
                    hours=Decimal(str(round(daily_hours, 2))),
                    note="Urlaub",
                )
                db.add(abs_)
                created.append(cur)
                budget_2026 -= 1
            cur += timedelta(days=1)

    # --- Krankheit 2026 ---
    sick_dates_2026 = []
    attempts = 0
    while len(sick_dates_2026) < profile["sick_count"] and attempts < 200:
        attempts += 1
        d = date(2026, 4, 1) + timedelta(days=random.randint(0, 274))  # Apr–Dez
        if is_workday(d, holiday_dates_2026) and d not in created and d not in sick_dates_2026:
            sick_dates_2026.append(d)
    for d in sick_dates_2026:
        abs_ = Absence(
            tenant_id=user.tenant_id,
            user_id=user.id,
            date=d,
            type=AbsenceType.SICK,
            hours=Decimal(str(round(daily_hours, 2))),
            note="Krankmeldung",
        )
        db.add(abs_)
        created.append(d)

    # --- Fortbildung ---
    for td in profile["training_dates"]:
        if is_workday(td, holiday_dates_2026) and td not in created:
            abs_ = Absence(
                tenant_id=user.tenant_id,
                user_id=user.id,
                date=td,
                type=AbsenceType.TRAINING,
                hours=Decimal(str(round(daily_hours, 2))),
                note="Fortbildung",
            )
            db.add(abs_)
            created.append(td)

    # --- Überstundenausgleich ---
    for cd in profile["overtime_comp_dates"]:
        if is_workday(cd, holiday_dates_2026) and cd not in created:
            abs_ = Absence(
                tenant_id=user.tenant_id,
                user_id=user.id,
                date=cd,
                type=AbsenceType.OVERTIME,
                hours=Decimal(str(round(daily_hours, 2))),
                note="Überstundenausgleich",
            )
            db.add(abs_)
            created.append(cd)

    # --- Jan/Feb 2027: 1-2 Krankheitstage ---
    sick_2027 = random.randint(0, 2)
    sick_done = 0
    for d_offset in range(0, 59):
        if sick_done >= sick_2027:
            break
        d = date(2027, 1, 1) + timedelta(days=d_offset)
        if is_workday(d, holiday_dates_2027) and d not in created:
            if random.random() < 0.05:  # ~5% Chance je Tag
                abs_ = Absence(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    date=d,
                    type=AbsenceType.SICK,
                    hours=Decimal(str(round(daily_hours, 2))),
                    note="Krankmeldung",
                )
                db.add(abs_)
                created.append(d)
                sick_done += 1

    db.commit()
    return set(created)


# ---------------------------------------------------------------------------
# 6. Zeiteinträge generieren
# ---------------------------------------------------------------------------

def get_work_weekdays(work_days_per_week):
    """Gibt die Wochentage (0=Mo, 4=Fr) zurück, an denen ein User arbeitet."""
    if work_days_per_week >= 5:
        return {0, 1, 2, 3, 4}  # Mo–Fr
    elif work_days_per_week == 4:
        return {0, 1, 2, 3}     # Mo–Do
    elif work_days_per_week == 3:
        return {0, 2, 4}        # Mo, Mi, Fr
    elif work_days_per_week == 2:
        return {0, 2}           # Mo, Mi
    else:
        return {0}              # nur Mo


def create_time_entries_for_user(db, user, profile, absence_dates,
                                  holiday_dates_2026, holiday_dates_2027):
    """Erstellt Zeiteinträge vom 01.01.2026 bis Feb 2027.

    Löscht nur Einträge ab April 2026 (wegen falscher Wochentage aus vorherigen Läufen).
    Füllt außerdem fehlende Tage in Jan-März nach (für vollständige Jahresberechnung).
    """
    from sqlalchemy import func

    # Bestehende Einträge ab April 2026 löschen (wegen falscher Wochentage)
    db.query(TimeEntry).filter(
        TimeEntry.user_id == user.id,
        TimeEntry.date >= date(2026, 4, 1),
    ).delete(synchronize_session=False)
    db.commit()

    # Bereits vorhandene Datumswerte laden (für Lücken-Füllung Jan–März)
    existing_dates = {
        row[0] for row in
        db.query(TimeEntry.date).filter(TimeEntry.user_id == user.id).all()
    }

    start_date = date(2026, 1, 1)
    end_date = date(2027, 2, 28)

    work_weekdays = get_work_weekdays(user.work_days_per_week or 5)
    daily_hours = float(user.weekly_hours) / len(work_weekdays)
    variance_min, variance_max = profile["daily_variance"]
    start_hour_min, start_hour_max = profile["start_hour_range"]

    cur = start_date
    entries_created = 0

    while cur <= end_date:
        hd = holiday_dates_2026 if cur.year == 2026 else holiday_dates_2027
        if cur in existing_dates:
            cur += timedelta(days=1)
            continue
        if cur.weekday() in work_weekdays and cur not in hd and cur not in absence_dates:
            # Startzeit
            sh = random.randint(start_hour_min, start_hour_max)
            sm = random.choice([0, 15, 30])
            start_t = time(sh, sm)

            # Effektive Arbeitsstunden
            target_h = daily_hours * random.uniform(variance_min, variance_max)

            # Pause: bei > 6h Pflicht
            if target_h > 6:
                break_min = random.choice(profile["break_choices"]) or 30
            else:
                break_min = random.choice([0] + profile["break_choices"])

            total_min = int(target_h * 60) + break_min
            end_dt = datetime.combine(cur, start_t) + timedelta(minutes=total_min)
            end_t = end_dt.time()

            # Max 22 Uhr
            if end_t.hour >= 22:
                end_t = time(21, 45)

            entry = TimeEntry(
                tenant_id=user.tenant_id,
                user_id=user.id,
                date=cur,
                start_time=start_t,
                end_time=end_t,
                break_minutes=break_min,
                note="",
            )
            db.add(entry)
            entries_created += 1

        cur += timedelta(days=1)

    db.commit()
    print(f"    → {entries_created} neue Zeiteinträge (Jan 2026 – Feb 2027, Lücken gefüllt)")


# ---------------------------------------------------------------------------
# 7. Jahresabschluss
# ---------------------------------------------------------------------------

def run_year_closing(db, year):
    """Berechnet Jahresabschluss für alle aktiven, track_hours-User."""
    print(f"\n  Jahresabschluss {year} wird berechnet...")

    # Bestehende Carryovers für year+1 löschen (falls vorhanden)
    db.query(YearCarryover).filter(
        YearCarryover.year == year + 1
    ).delete(synchronize_session=False)
    db.commit()

    users = db.query(User).filter(
        User.is_active == True,
        User.track_hours == True,
    ).all()

    results = calculation_service.create_year_closing(db, year, users)

    for r in results:
        print(f"    {r['first_name']} {r['last_name']}: "
              f"OT={r['overtime_hours']:+.1f}h, "
              f"Resturlaub={r['vacation_days']:.1f}d → Carryover {year+1}")
    return results


# ---------------------------------------------------------------------------
# 8. Hauptprogramm
# ---------------------------------------------------------------------------

def main():
    print("=" * 65)
    print("PraxisZeit – Testdaten-Setup (Anonymisierung + Apr2026–Feb2027)")
    print("=" * 65)

    db = SessionLocal()
    set_superadmin_context(db)

    # 1. Anonymisieren
    anonymize_users(db)

    # 2. Bereinigen
    cleanup_future_data(db)

    # Feiertage laden
    hd_2026 = get_holiday_dates(db, 2026)
    hd_2027 = get_holiday_dates(db, 2027)
    print(f"\n  Feiertage geladen: {len(hd_2026)} (2026), {len(hd_2027)} (2027)")

    # 3. Testdaten pro Mitarbeiter
    print("\n=== Schritt 3: Testdaten generieren ===")

    for username, profile in PROFILES.items():
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"  ! User {username} nicht gefunden – übersprungen")
            continue

        print(f"\n  {user.first_name} {user.last_name} ({user.weekly_hours}h/w):")

        new_absence_dates = create_absences_for_user(
            db, user, profile, hd_2026, hd_2027
        )
        # Alle Abwesenheiten des Users laden (inkl. bestehende Jan-März)
        all_absences = db.query(Absence).filter(Absence.user_id == user.id).all()
        all_absence_dates = {a.date for a in all_absences}
        print(f"    → {len(new_absence_dates)} neue Abwesenheitstage, {len(all_absence_dates)} gesamt")

        create_time_entries_for_user(
            db, user, profile, all_absence_dates, hd_2026, hd_2027
        )

    # 4. Jahresabschlüsse
    print("\n=== Schritt 4: Jahresabschlüsse ===")
    r2025 = run_year_closing(db, 2025)
    r2026 = run_year_closing(db, 2026)

    db.close()

    print("\n" + "=" * 65)
    print("✓ Fertig!")
    print("  Jahresabschluss 2025 → Carryover 2026 erstellt")
    print("  Jahresabschluss 2026 → Carryover 2027 erstellt")
    print("  Alle Testdaten bis Feb 2027 vorhanden")
    print("=" * 65)


if __name__ == "__main__":
    main()
