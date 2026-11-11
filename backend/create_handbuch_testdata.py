"""
Demodaten fuer die Handbuch-Screenshots (Praxis am Lindenplatz).

Alle Daten haengen an einem Stichtag (Standard: der Mittwoch der Kalenderwoche,
die 14 Tage vor heute liegt). Zeiteintraege laufen vom 1. des Vormonats bis zum
Stichtag; Urlaub, Antraege, Betriebsferien usw. liegen relativ dazu. So wirken
die Aufnahmen aktuell, egal wann der Seed laeuft.

    python create_handbuch_testdata.py [--stichtag YYYY-MM-DD]

Letzte Ausgabezeile: ``STICHTAG=YYYY-MM-DD``.

Schreibwege laufen ueber die ORM-Session unter ``set_superadmin_context`` und
tragen ``tenant_id`` an jeder Zeile (Lehre B9: kein Commit an der Session
vorbei, sonst fehlt der Mandantenkontext). Im Superadmin-Kontext greift RLS
nicht — jede Abfrage filtert den Mandanten selbst.
"""
import argparse
import sys
import uuid
from datetime import date, datetime, timedelta, timezone, time as dt_time
from decimal import Decimal
import random
from zoneinfo import ZoneInfo

sys.path.insert(0, '/app')

from app.database import SessionLocal, set_superadmin_context
from app.models import (
    User, TimeEntry, Absence, PublicHoliday, AbsenceType,
    WorkingHoursChange, ChangeRequest, CompanyClosure, ReducedDay,
    VacationRequest, SystemSetting, YearCarryover,
    Workstation, ShiftPlan, ShiftSlot, ShiftAssignment, WorkstationQualification,
)
from app.models.absence import AbsenceReason
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.models.user import UserRole
from app.models.vacation_request import VacationRequestStatus
from app.services import auth_service
from app.services import calculation_service
from app.services import holiday_service
from app.services import work_window_service
from app.services.work_blocks_service import derive_targets

random.seed(42)  # Reproduzierbar

# Default tenant UUID (on-prem single-tenant bootstrap).
TENANT_ID = "00000000-0000-0000-0000-000000000001"
BERLIN = ZoneInfo("Europe/Berlin")

PASSWORD = "Handbuch2026!"
MAIL_DOMAIN = "praxis-lindenplatz.example"
ADMIN_EMAIL = f"admin@{MAIL_DOMAIN}"

REASON_NAME = "Fortbildung extern"
CLOSURE_NAME = "Teamklausur"
REDUCED_DAY_LABEL = "Brückentag"
REDUCED_DAY_MAX_HOURS = Decimal("4.00")
# Schichtplan (#305): ein heute gültiger Wochenplan, sichtbar für alle Mitarbeitenden.
# Die Planung ist vom Rechenmodell entkoppelt; sichtbar wird sie erst, wenn eine
# Aufnahme ``shift_planning_enabled`` einschaltet (Standard aus).
SHIFT_PLAN_NAME = "Wochenplan Praxis"
SHIFT_PLAN_DESCRIPTION = "Gilt bis auf Weiteres. Tauschwünsche bitte an Dr. Werner."
SHIFT_WORKSTATIONS = [  # (Name, Farbe)
    ("Anmeldung", "#BFDBFE"),
    ("Labor", "#BBF7D0"),
]
# (Arbeitsplatz, Wochentag 0=Mo, Beginn, Ende, Mindestbesetzung, Hinweis, Benutzernamen).
# Höchstens zwei Schichten gleichzeitig je Tag, damit das Wochenraster lesbar bleibt.
SHIFT_SLOTS = [
    ("Anmeldung", 0, "07:45", "12:00", 1, None, ["maria"]),
    ("Anmeldung", 1, "07:45", "12:00", 1, None, ["petra"]),
    ("Anmeldung", 2, "07:45", "12:00", 1, "Telefondienst bis 9:00", ["maria"]),
    ("Anmeldung", 3, "07:45", "12:00", 1, None, ["petra"]),
    ("Anmeldung", 4, "07:45", "12:00", 1, None, ["maria"]),
    ("Anmeldung", 0, "12:00", "16:15", 1, None, ["thomas"]),
    ("Anmeldung", 1, "12:00", "16:15", 1, None, ["julia"]),
    ("Anmeldung", 2, "12:00", "16:15", 1, None, ["maria"]),
    ("Anmeldung", 3, "12:00", "16:15", 1, None, ["julia"]),
    ("Anmeldung", 4, "12:00", "16:15", 1, None, ["thomas"]),
    ("Labor", 0, "08:00", "12:00", 1, None, ["sarah"]),
    ("Labor", 1, "08:00", "12:00", 1, None, ["sarah"]),
    ("Labor", 2, "08:00", "12:00", 1, "Blutabnahmen nüchtern bis 10:00", ["sarah"]),
    ("Labor", 3, "08:00", "12:00", 1, None, ["sarah"]),
    ("Labor", 4, "08:00", "13:00", 1, None, ["sarah"]),
    ("Labor", 1, "12:00", "16:15", 1, None, ["thomas"]),
    ("Labor", 2, "12:00", "16:15", 1, None, ["thomas"]),
    ("Labor", 3, "12:00", "16:15", 1, None, ["thomas"]),
]
# Thomas hat an diesem Werktag vor dem Stichtag vergessen zu stempeln (kein
# Eintrag) — Handbuch-Aufnahme ``ma-vergangener-tag`` füllt {{werktag-4}}.
# Nicht Maria: ihr Dashboard ist die Übersichtsaufnahme ohne „Buchung fehlt“ (R19).
THOMAS_FORGOTTEN_WORKDAY = 4

# Sarah: Arbeitszeit-Blöcke Mo–Do 08–12 + 15–16, Fr 08–13 (25 h)
SARAH_BLOCKS = [
    {"blocks": [{"start": "08:00", "end": "12:00"}, {"start": "15:00", "end": "16:00"}],
     "pause_minutes": 0}
    for _ in range(4)
] + [{"blocks": [{"start": "08:00", "end": "13:00"}], "pause_minutes": 0}]
# Sarahs früherer Vertrag (vor der Arbeitszeit-Änderung): 20 h, Mo–Fr 08–12
SARAH_OLD_BLOCKS = [
    {"blocks": [{"start": "08:00", "end": "12:00"}], "pause_minutes": 0} for _ in range(5)
]

# ── Personas ──────────────────────────────────────────────────────────────────
# ``day_hours`` = Tagesplan (Mo–Fr); None = gleichmäßig auf work_days_per_week.
EMPLOYEES = [
    {
        "username": "maria", "first_name": "Maria", "last_name": "Hoffmann",
        "weekly_hours": Decimal("40.0"), "work_days_per_week": 5, "vacation_days": 30,
        "calendar_color": "#93C5FD",
    },
    {
        "username": "thomas", "first_name": "Thomas", "last_name": "Bauer",
        "weekly_hours": Decimal("38.5"), "work_days_per_week": 5, "vacation_days": 28,
        "calendar_color": "#86EFAC",
    },
    {
        "username": "sarah", "first_name": "Sarah", "last_name": "Klein",
        "weekly_hours": Decimal("25.0"), "work_days_per_week": 5, "vacation_days": 20,
        "calendar_color": "#F9A8D4",
        "work_blocks": SARAH_BLOCKS,
    },
    {
        "username": "petra", "first_name": "Petra", "last_name": "Schulz",
        "weekly_hours": Decimal("20.0"), "work_days_per_week": 4, "vacation_days": 16,
        "calendar_color": "#FDBA74",
        "day_hours": [Decimal("5.00")] * 4 + [None],          # Mo–Do
    },
    {
        "username": "julia", "first_name": "Julia", "last_name": "Meyer",
        "weekly_hours": Decimal("10.0"), "work_days_per_week": 2, "vacation_days": 8,
        "calendar_color": "#C4B5FD",
        "milog_working_time_account": True,                    # Minijob
        "day_hours": [None, Decimal("5.00"), None, Decimal("5.00"), None],  # Di, Do
    },
]

# Gespiegelt aus frontend/src/handbuch/settingsRestore.ts (SETTING_DEFAULTS): als
# Zeilen angelegt, damit das Zurückstellen nach einer Aufnahme nie von
# doppelt gepflegten Defaults abhängt. Ein Test vergleicht beide Listen.
SETTING_DEFAULTS = {
    "break_exception_allowed": "true",
    "break_exception_requires_approval": "false",
    "vacation_approval_required": "false",
    "closure_overtime_after_vacation": "false",
    "work_window_grace_minutes": "15",
    "onboarding_enabled": "true",
    "shift_planning_enabled": "false",
    "shift_planning_weekdays": "0,1,2,3,4",
    "child_sick_days_default": "15",
    "show_year_end_overtime_employee_dashboard": "true",
    "show_year_end_overtime_admin_dashboard": "true",
    "special_day_dec24_mode": "working_day",
    "special_day_dec31_mode": "working_day",
    "special_day_dec24_counts_as_vacation": "true",
    "special_day_dec31_counts_as_vacation": "true",
    "special_day_dec24_max_hours": "4",
    "special_day_dec31_max_hours": "4",
}

HOURS_FIELDS = ("hours_monday", "hours_tuesday", "hours_wednesday", "hours_thursday", "hours_friday")


# ── Datumshilfen ──────────────────────────────────────────────────────────────

def _is_workday(d: date, holiday_dates) -> bool:
    return d.weekday() < 5 and d not in holiday_dates


def default_stichtag(today: date, holiday_dates=()) -> date:
    """Mittwoch der Kalenderwoche, die 14 Tage vor ``today`` liegt; ist das ein
    Feiertag, der nächste Werktag."""
    ref = today - timedelta(days=14)
    d = ref - timedelta(days=ref.weekday()) + timedelta(days=2)
    while not _is_workday(d, holiday_dates):
        d += timedelta(days=1)
    return d


def prev_month_start(stichtag: date) -> date:
    return (stichtag.replace(day=1) - timedelta(days=1)).replace(day=1)


def data_start(stichtag: date) -> date:
    """Beginn der Demodaten: 1. des Vormonats, spätestens der 1. Januar des
    Stichtag-Jahres (Jahres-/YTD-Ansichten zeigen so realistische Salden).
    ``first_work_day`` bleibt bewusst ungesetzt (sonst anteiliger Urlaub)."""
    return min(prev_month_start(stichtag), date(stichtag.year, 1, 1))


def is_half_special_day(d: date) -> bool:
    """24./31.12. — der Seed stellt beide auf ``half_day``."""
    return (d.month, d.day) in ((12, 24), (12, 31))


def pick_run(start: date, n: int, holiday_dates) -> list:
    """Erste Folge von ``n`` aufeinanderfolgenden Werktagen (Mo–Fr, ohne
    Feiertag) ab ``start`` — beginnt nur an einem Montag, wenn n > 1."""
    d = start
    while True:
        run = [d + timedelta(days=i) for i in range(n)]
        # Halbtags-Sondertage (24./31.12.) nie in Buchungsfolgen
        if (n == 1 or d.weekday() == 0) and all(_is_workday(x, holiday_dates) for x in run) \
                and not any(is_half_special_day(x) for x in run) and run[-1].weekday() < 5:
            return run
        d += timedelta(days=1)


def workday_before(stichtag: date, n: int) -> date:
    """N-ter Werktag (Mo–Fr, Feiertage zählen mit) vor dem Stichtag — Spiegel
    von ``workdayBefore`` in frontend/src/handbuch/dates.ts ({{werktag-N}})."""
    d = stichtag
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def prev_workday(d: date, holiday_dates) -> date:
    while not _is_workday(d, holiday_dates):
        d -= timedelta(days=1)
    return d


def get_holiday_dates(db, start: date, end: date) -> set:
    # Superadmin-Kontext: RLS greift nicht, der Mandantenfilter ist Pflicht
    # (Gesamtreview 1.20 B9) — sonst strichen Feiertage fremder Mandanten
    # Arbeitstage aus dem Demo-Zeitraum.
    holidays = db.query(PublicHoliday).filter(
        PublicHoliday.tenant_id == TENANT_ID,
        PublicHoliday.date >= start,
        PublicHoliday.date <= end,
    ).all()
    return {h.date for h in holidays}


def ensure_holidays(db, start: date, end: date) -> None:
    """Feiertage der betroffenen Jahre nachtragen, wenn der Mandant für ein Jahr
    keine hat (Bootstrap legt nur laufendes + nächstes Jahr an)."""
    state = holiday_service.get_holiday_state(db, TENANT_ID)
    for year in range(start.year, end.year + 1):
        n = db.query(PublicHoliday).filter(
            PublicHoliday.tenant_id == TENANT_ID, PublicHoliday.year == year,
        ).count()
        if n == 0:
            added = holiday_service.sync_holidays(db, year, state, tenant_id=TENANT_ID)
            print(f"  ~ Feiertage {year} ({state}) nachgetragen: {added}")
    db.commit()


# ── Konten ────────────────────────────────────────────────────────────────────

def update_admin_password(db):
    """Admin (aus dem Bootstrap) umbenennen und Passwort setzen — nie löschen."""
    admin = db.query(User).filter(
        User.username == "admin",
        User.tenant_id == TENANT_ID,  # Superadmin-Kontext: nie das Admin-Konto eines fremden Mandanten
    ).first()
    if admin:
        admin.first_name = "Dr. Andrea"
        admin.last_name = "Werner"
        admin.email = ADMIN_EMAIL
        admin.password_hash = auth_service.hash_password(PASSWORD)
        admin.onboarding_completed_at = datetime.now(timezone.utc)
        db.commit()
        print(f"  ✓ Admin: Dr. Andrea Werner, Passwort gesetzt ({PASSWORD})")
    else:
        print("  ! Admin-User nicht gefunden")
    return admin


def _purge_existing(db, usernames) -> None:
    """Gleichnamige Konten samt abhängiger Zeilen entfernen (Art.-17-Muster aus
    ``admin_users.purge_user``, soweit der Seed Zeilen anlegt). Für die frische
    Wegwerf-DB gedacht; Protokollzeilen (``time_entry_audit_logs``) legt der
    Seed nie an und darf sie als App-Konto auch nicht löschen."""
    # Betriebsferien des Seeds (Abwesenheiten.closure_id ist SET NULL; die
    # Abwesenheiten der Demo-Konten gehen unten mit den Konten)
    db.query(CompanyClosure).filter(
        CompanyClosure.tenant_id == TENANT_ID, CompanyClosure.name == CLOSURE_NAME,
    ).delete(synchronize_session=False)
    # Schichtplan des Seeds: Plan zuerst (Schichten und Einteilungen hängen per
    # ON DELETE CASCADE daran), danach die Arbeitsplätze (Einweisungen CASCADE;
    # Schichten verweisen RESTRICT und sind dann schon weg).
    db.query(ShiftPlan).filter(
        ShiftPlan.tenant_id == TENANT_ID, ShiftPlan.name == SHIFT_PLAN_NAME,
    ).delete(synchronize_session=False)
    db.query(Workstation).filter(
        Workstation.tenant_id == TENANT_ID,
        Workstation.name.in_([name for name, _ in SHIFT_WORKSTATIONS]),
    ).delete(synchronize_session=False)
    existing = db.query(User).filter(
        User.tenant_id == TENANT_ID, User.username.in_(list(usernames)),
    ).all()
    if not existing:
        db.commit()
        return
    ids = [u.id for u in existing]
    t = TENANT_ID
    db.query(ChangeRequest).filter(ChangeRequest.tenant_id == t, ChangeRequest.reviewed_by.in_(ids)
                                   ).update({ChangeRequest.reviewed_by: None}, synchronize_session=False)
    db.query(VacationRequest).filter(VacationRequest.tenant_id == t, VacationRequest.reviewed_by.in_(ids)
                                     ).update({VacationRequest.reviewed_by: None}, synchronize_session=False)
    for model in (ChangeRequest, VacationRequest, WorkingHoursChange, TimeEntry, Absence, YearCarryover):
        db.query(model).filter(model.tenant_id == t, model.user_id.in_(ids)).delete(synchronize_session=False)
    db.flush()
    for u in existing:
        db.delete(u)
    db.commit()
    print(f"  ~ {len(existing)} bestehende Demo-Konten gelöscht und neu angelegt")


def _apply_blocks(user: User, blocks) -> None:
    """Blöcke samt abgeleitetem Soll auf die User-Zeile (Rückfall + Spiegel)."""
    user.work_blocks = blocks
    for field, value in derive_targets(blocks).items():
        setattr(user, field, value)


def create_employees(db) -> list:
    _purge_existing(db, [e["username"] for e in EMPLOYEES])
    created = []
    for emp in EMPLOYEES:
        u = User(
            tenant_id=TENANT_ID,
            username=emp["username"],
            email=f"{emp['first_name'].lower()}.{emp['last_name'].lower()}@{MAIL_DOMAIN}",
            first_name=emp["first_name"],
            last_name=emp["last_name"],
            password_hash=auth_service.hash_password(PASSWORD),
            role=UserRole.EMPLOYEE,
            weekly_hours=emp["weekly_hours"],
            work_days_per_week=emp["work_days_per_week"],
            vacation_days=emp["vacation_days"],
            calendar_color=emp["calendar_color"],
            track_hours=True,
            is_night_worker=False,
            exempt_from_arbzg=False,
            milog_working_time_account=emp.get("milog_working_time_account", False),
            is_active=True,
            is_hidden=False,
            onboarding_completed_at=datetime.now(timezone.utc),
        )
        if emp.get("day_hours"):
            u.use_daily_schedule = True
            for field, value in zip(HOURS_FIELDS, emp["day_hours"]):
                setattr(u, field, value)
        if emp.get("work_blocks"):
            _apply_blocks(u, emp["work_blocks"])
        db.add(u)
        db.commit()
        db.refresh(u)
        created.append(u)
        print(f"  ✓ {emp['first_name']} {emp['last_name']} ({emp['weekly_hours']} h/Woche) angelegt")
    return created


# ── Vertragsverlauf ───────────────────────────────────────────────────────────

def _snapshot_row(user: User, effective_from: date, *, weekly_hours, work_days, vacation_days,
                  blocks=None, day_hours=None, note=None, created_at=None) -> WorkingHoursChange:
    """Vollständiger Vertrags-Snapshot (wie ``admin_users._frozen_row``/Anlegen)."""
    values = {f: None for f in HOURS_FIELDS}
    use_daily = False
    if blocks:
        derived = derive_targets(blocks)
        weekly_hours, work_days = derived["weekly_hours"], derived["work_days_per_week"]
        use_daily = True
        values = {f: derived[f] for f in HOURS_FIELDS}
    elif day_hours:
        use_daily = True
        values = dict(zip(HOURS_FIELDS, day_hours))
    return WorkingHoursChange(
        tenant_id=TENANT_ID, user_id=user.id, effective_from=effective_from,
        weekly_hours=weekly_hours, use_daily_schedule=use_daily, work_days_per_week=work_days,
        blocks=blocks, vacation_days=vacation_days, track_hours=user.track_hours,
        milog_working_time_account=user.milog_working_time_account,
        agreed_monthly_hours=None, use_fixed_monthly_target=False,
        note=note, **values,
        # Handbuch: „Erstellt:“ im Verlauf realistisch statt der Seed-Uhr
        **({"created_at": created_at} if created_at is not None else {}),
    )


def create_contract_history(db, users: list, stichtag: date) -> None:
    """Sarah: Arbeitszeit-Änderung mitten im Vormonat (20 h → 25 h mit Blöcken).
    Petra: Urlaubsanspruch ab Monatsanfang geändert (Vertragsverlauf-Felder)."""
    by_name = {u.username: u for u in users}
    prev_start = prev_month_start(stichtag)
    base_from = data_start(stichtag)  # Ausgangsvertrag gilt ab Datenbeginn
    month_start = stichtag.replace(day=1)

    sarah = by_name.get("sarah")
    if sarah:
        change_from = prev_start + timedelta(days=14)
        change_from -= timedelta(days=change_from.weekday())  # Montag der Woche
        if change_from <= prev_start:
            change_from += timedelta(days=7)
        db.add(_snapshot_row(sarah, base_from, weekly_hours=None, work_days=None,
                             vacation_days=sarah.vacation_days, blocks=SARAH_OLD_BLOCKS,
                             note="Ausgangsvertrag", created_at=_berlin(base_from, 9, 0)))
        db.add(_snapshot_row(sarah, change_from, weekly_hours=None, work_days=None,
                             vacation_days=sarah.vacation_days, blocks=SARAH_BLOCKS,
                             note="Aufstockung auf 25 Wochenstunden",
                             # eine Woche vorher vereinbart und eingetragen
                             created_at=_berlin(change_from - timedelta(days=7), 14, 10)))
        print(f"  ✓ Sarah: Arbeitszeit-Änderung ab {change_from}")

    petra = by_name.get("petra")
    if petra:
        emp = next(e for e in EMPLOYEES if e["username"] == "petra")
        new_days = Decimal("18.0")
        db.add(_snapshot_row(petra, base_from, weekly_hours=emp["weekly_hours"], work_days=4,
                             vacation_days=petra.vacation_days, day_hours=emp["day_hours"],
                             note="Ausgangsvertrag", created_at=_berlin(base_from, 9, 5)))
        db.add(_snapshot_row(petra, month_start, weekly_hours=emp["weekly_hours"], work_days=4,
                             vacation_days=new_days, day_hours=emp["day_hours"],
                             note="Urlaubsanspruch auf 18 Tage erhöht",
                             created_at=_berlin(month_start - timedelta(days=6), 11, 20)))
        petra.vacation_days = new_days  # User-Zeile spiegelt die jüngste Zeile
        print(f"  ✓ Petra: Urlaubsanspruch 16 → 18 ab {month_start}")
    db.commit()


# ── Einstellungen, Grund, verkürzter Tag ──────────────────────────────────────

def _set_setting(db, key: str, value: str) -> None:
    row = db.query(SystemSetting).filter(
        SystemSetting.key == key, SystemSetting.tenant_id == TENANT_ID,
    ).first()
    if row:
        row.value = value
    else:
        # Teil des Primärschlüssels: echte UUID (Insert-Sentinel-Abgleich)
        db.add(SystemSetting(key=key, tenant_id=uuid.UUID(str(TENANT_ID)), value=value))
    db.flush()  # Session ohne autoflush: spätere Abfrage desselben Schlüssels muss die Zeile sehen


def create_settings_and_catalog(db, admin, stichtag: date, holiday_dates) -> date:
    """Sondertage 24./31.12. als halber Tag, Urlaubsanträge mit Genehmigung,
    eigener Abwesenheitsgrund, ein verkürzter Tag. Gibt dessen Datum zurück."""
    for key, value in SETTING_DEFAULTS.items():  # erst die Defaults, dann die Demo-Werte
        _set_setting(db, key, value)
    _set_setting(db, "special_day_dec24_mode", "half_day")
    _set_setting(db, "special_day_dec31_mode", "half_day")
    _set_setting(db, "vacation_approval_required", "true")

    db.query(ReducedDay).filter(ReducedDay.tenant_id == TENANT_ID).delete(synchronize_session=False)
    db.query(AbsenceReason).filter(
        AbsenceReason.tenant_id == TENANT_ID, AbsenceReason.name == REASON_NAME,
    ).delete(synchronize_session=False)
    db.add(AbsenceReason(tenant_id=TENANT_ID, name=REASON_NAME, color="#A78BFA",
                         base_behavior="worked", is_active=True, sort_order=0))
    # Freitag der Vorwoche
    reduced = prev_workday(stichtag - timedelta(days=5), holiday_dates)
    db.add(ReducedDay(tenant_id=TENANT_ID, date=reduced, label=REDUCED_DAY_LABEL,
                      max_hours=REDUCED_DAY_MAX_HOURS, created_by=admin.id if admin else None))
    db.commit()
    print(f"  ✓ Sondertage 24./31.12. = halber Tag; verkürzter Tag {reduced} (max. 4 h); Grund „{REASON_NAME}“")
    return reduced


# ── Abwesenheiten, Urlaubsantrag, Betriebsferien ──────────────────────────────

def _day_target(db, user: User, d: date) -> Decimal:
    """Tagessoll laut Vertrags-Snapshot zum Datum (Abwesenheiten buchen das)."""
    sched = calculation_service.get_schedule_for_date(db, user, d)
    return calculation_service.get_daily_target_for_date(user, d, sched)


def create_absences(db, users: list, admin, stichtag: date, holiday_dates) -> None:
    by_name = {u.username: u for u in users}
    reason = db.query(AbsenceReason).filter(
        AbsenceReason.tenant_id == TENANT_ID, AbsenceReason.name == REASON_NAME,
    ).first()

    def book(user, d, absence_type, note, **extra):
        hours = _day_target(db, user, d)
        if hours <= 0:
            return False
        db.add(Absence(tenant_id=TENANT_ID, user_id=user.id, date=d, end_date=None,
                       type=absence_type, hours=hours, note=note, **extra))
        return True

    maria, thomas, sarah = by_name.get("maria"), by_name.get("thomas"), by_name.get("sarah")
    if maria:  # Urlaub vergangen, 3 Tage (Mo–Mi, drei Wochen vor dem Stichtag)
        run = pick_run(stichtag - timedelta(days=23), 3, holiday_dates)
        for d in run:
            book(maria, d, AbsenceType.VACATION, "Kurzurlaub")
        # genehmigter Antrag dazu (vacation_approval_required=true): die
        # Abwesenheiten oben sind das Ergebnis der Genehmigung. Gestellt drei
        # Wochen vor dem Urlaub, genehmigt am Folgetag — sonst zeigt „Meine
        # Anträge" „Gestellt: <Stichtag>" für einen längst vergangenen Urlaub.
        asked = datetime.combine(run[0] - timedelta(days=21), dt_time(9, 12), tzinfo=BERLIN)
        db.add(VacationRequest(
            tenant_id=TENANT_ID, user_id=maria.id, date=run[0], end_date=run[-1],
            hours=_day_target(db, maria, run[0]), absence_type="vacation", half_day=False,
            note="Kurzurlaub", status=VacationRequestStatus.APPROVED.value,
            reviewed_by=admin.id if admin else None, reviewed_at=asked + timedelta(days=1, hours=2),
            created_at=asked, updated_at=asked + timedelta(days=1, hours=2),
        ))
    if sarah:  # Krank, 2 Tage
        d1 = prev_workday(stichtag - timedelta(days=15), holiday_dates)
        d2 = d1 + timedelta(days=1)
        while not _is_workday(d2, holiday_dates):
            d2 += timedelta(days=1)
        for d in (d1, d2):
            book(sarah, d, AbsenceType.SICK, "Erkältung")
    if thomas and reason:  # eigener Grund „Fortbildung extern"
        d = pick_run(stichtag - timedelta(days=9), 1, holiday_dates)[0]
        book(thomas, d, AbsenceType.TRAINING, "Ultraschallkurs", reason_id=reason.id)

    # Betriebsferien (Zukunft, 3 Tage, alle)
    closure_days = pick_run(stichtag + timedelta(days=21), 3, holiday_dates)
    closure = CompanyClosure(
        tenant_id=TENANT_ID, name=CLOSURE_NAME, start_date=closure_days[0], end_date=closure_days[-1],
        counts_as_vacation=True, created_by=admin.id if admin else users[0].id,
    )
    db.add(closure)
    db.flush()
    booked = 0
    for u in users:
        for d in closure_days:
            if book(u, d, AbsenceType.VACATION, f"Betriebsferien: {CLOSURE_NAME}", closure_id=closure.id):
                booked += 1
    print(f"  ✓ Betriebsferien {closure_days[0]}–{closure_days[-1]} ({booked} Abwesenheitstage)")

    # offener Urlaubsantrag Thomas (Zukunft, 5 Tage, nach den Betriebsferien)
    if thomas:
        run = pick_run(closure_days[-1] + timedelta(days=7), 5, holiday_dates)
        db.add(VacationRequest(
            tenant_id=TENANT_ID, user_id=thomas.id, date=run[0], end_date=run[-1],
            hours=_day_target(db, thomas, run[0]), absence_type="vacation", half_day=False,
            note="Familienurlaub", status=VacationRequestStatus.PENDING.value,
            # am Vortag des Stichtags gestellt — nicht in der Aufnahme-Minute
            created_at=_berlin(prev_workday(stichtag - timedelta(days=1), holiday_dates), 16, 20),
            updated_at=_berlin(prev_workday(stichtag - timedelta(days=1), holiday_dates), 16, 20),
        ))
        print(f"  ✓ Urlaubsantrag Thomas (offen) {run[0]}–{run[-1]}")
    db.commit()


# ── Zeiteinträge ──────────────────────────────────────────────────────────────

def _minutes_to_time(minutes: int) -> dt_time:
    return dt_time(minutes // 60, minutes % 60)


def _block_spans(db, user: User, d: date, through: bool, cap_hours):
    day_blocks = work_window_service.get_scheduled_blocks(db, user, d)
    if not day_blocks:
        return []
    if through:
        return [(day_blocks[0][0], day_blocks[-1][1])]
    if cap_hours is None:
        return list(day_blocks)
    spans, credited = [], 0
    limit = int(float(cap_hours) * 60)
    for blk in day_blocks:  # verkürzter Tag: Blöcke, bis die Obergrenze erreicht ist
        if credited >= limit:
            break
        s_min, e_min = blk
        if credited + (e_min - s_min) > limit:  # letzten Block auf die Obergrenze kürzen
            e_min = s_min + (limit - credited)
        spans.append((s_min, e_min))
        credited += e_min - s_min
    return spans


def _plain_entry(user: User, d: date, target_hours: float, capped: bool = False) -> TimeEntry:
    start = dt_time(random.randint(7, 9), random.choice([0, 15, 30, 45]))
    net = round(target_hours * random.uniform(0.92, 1.08) * 4) / 4
    if capped:  # verkürzter Tag: nie über die Obergrenze
        net = min(net, target_hours)
    break_min = 45 if net > 6 else 0  # §4 ArbZG: > 6 h → mindestens 30 min
    end = (datetime.combine(d, start) + timedelta(minutes=int(net * 60) + break_min)).time()
    return TimeEntry(tenant_id=TENANT_ID, user_id=user.id, date=d, start_time=start,
                     end_time=end, break_minutes=break_min, note="")


def create_time_entries_for_user(db, user: User, holiday_dates: set, start: date, end: date,
                                 stichtag: date = None) -> int:
    """Zeiteinträge für jeden Werktag mit Soll in ``[start, end]`` — ohne
    Feiertage und ohne Tage mit Abwesenheit. Mit ``stichtag``: Maria hat dort
    einen offenen Eintrag ab 07:45 („läuft"), Thomas einen §4-Befund mit Grund."""
    absence_dates = {
        a.date for a in db.query(Absence).filter(
            Absence.user_id == user.id, Absence.tenant_id == TENANT_ID,
        ).all()
    }
    reduced = {
        r.date: r.max_hours for r in db.query(ReducedDay).filter(
            ReducedDay.tenant_id == TENANT_ID, ReducedDay.date >= start, ReducedDay.date <= end,
        ).all()
    }
    days = []
    d = start
    while d <= end:
        if _is_workday(d, holiday_dates) and d not in absence_dates and _day_target(db, user, d) > 0:
            days.append(d)
        d += timedelta(days=1)

    through_days = set()
    if getattr(user, "work_blocks", None):
        # Durchgestempelt über die Mittagslücke → „zwischen den Blöcken nicht angerechnet"
        cands = [x for x in days if x.weekday() < 4 and x not in reduced
                 and len(work_window_service.get_scheduled_blocks(db, user, x)) > 1]
        through_days = {cands[i] for i in (-3, -8) if len(cands) >= -i}

    waiver_day = None
    if stichtag and user.username == "thomas" and len(days) >= 8:
        waiver_day = days[-6] if days[-6] not in reduced else days[-7]
    if stichtag and user.username == "thomas":
        # erst nach der Wahl des §4-Tages, damit dieser stabil bleibt
        forgotten = workday_before(stichtag, THOMAS_FORGOTTEN_WORKDAY)
        if forgotten == waiver_day:
            waiver_day = days[days.index(forgotten) - 1]
        days = [x for x in days if x != forgotten]

    grace = work_window_service.get_grace_minutes(db, TENANT_ID)
    count = 0
    for d in days:
        if stichtag and d == stichtag and user.username != "maria":
            # Die Aufnahme laeuft am Stichtag um 10:30 — kein Eintrag darf in der
            # Zukunft enden. Mit Bloecken: seit Blockbeginn eingestempelt (offen,
            # wie clock_in); sonst noch nicht eingestempelt. Maria s. u.
            day_blocks = work_window_service.get_scheduled_blocks(db, user, d)
            if getattr(user, "work_blocks", None) and day_blocks and day_blocks[0][0] <= 10 * 60 + 30:
                r = work_window_service.clamp(
                    db, user, d, _minutes_to_time(day_blocks[0][0]), None,
                    grace, credit_override=False,
                )
                db.add(TimeEntry(
                    tenant_id=TENANT_ID, user_id=user.id, date=d,
                    start_time=r.eff_start, end_time=None, raw_start_time=r.raw_start,
                    uncredited_minutes=r.uncredited_minutes, clamp_grace_minutes=r.grace_minutes,
                    break_minutes=0, note="",
                ))
                count += 1
            continue
        cap = reduced.get(d)
        if cap is None and is_half_special_day(d):  # halber Tag: halbes Tagessoll
            cap = _day_target(db, user, d) / 2
        if getattr(user, "work_blocks", None):
            for s_min, e_min in _block_spans(db, user, d, d in through_days, cap):
                r = work_window_service.clamp(
                    db, user, d, _minutes_to_time(s_min), _minutes_to_time(e_min),
                    grace, credit_override=False,
                )
                db.add(TimeEntry(
                    tenant_id=TENANT_ID, user_id=user.id, date=d,
                    start_time=r.eff_start, end_time=r.eff_end,
                    raw_start_time=r.raw_start, raw_end_time=r.raw_end,
                    uncredited_minutes=r.uncredited_minutes,
                    clamp_grace_minutes=r.grace_minutes,
                    break_minutes=0, note="",
                ))
                count += 1
            continue
        target = float(_day_target(db, user, d))
        if cap is not None:
            target = min(target, float(cap))
        entry = _plain_entry(user, d, target, capped=cap is not None)
        if stichtag and user.username == "maria" and d == stichtag:
            entry.start_time, entry.end_time, entry.break_minutes = dt_time(7, 45), None, 0
        if d == waiver_day:  # §4-Befund: 6:30 h ohne Pause, Ausnahme mit Grund
            entry.start_time, entry.end_time, entry.break_minutes = dt_time(8, 0), dt_time(14, 30), 0
            entry.break_waiver_reason = "Notfallpatient: Unterbrechung der Behandlung war nicht möglich."
        db.add(entry)
        count += 1
    db.commit()
    print(f"    ✓ {count} Zeiteinträge erstellt")
    return count


# ── Korrekturanträge ──────────────────────────────────────────────────────────

def _add_change_request(db, user, entry, status, prop_start, prop_end, prop_break,
                        reason, rejection_reason=None, reviewer=None, created_at=None, reviewed_at=None,
                        request_credit_override=False):
    """Legt einen UPDATE-Korrekturantrag über die Session an — mit Vorher-Bild
    wie ``change_requests.create_change_request`` und, wenn abgelehnt, mit
    Prüferin und Zeitpunkt wie ``review_change_request``.

    Gesamtreview 1.20 (B9): früher ein INSERT über die rohe DBAPI-Verbindung mit
    eigenem ``commit()``. Der Mandantenkontext steht per ``SET LOCAL`` nur in der
    laufenden Transaktion und wird über das ``after_begin``-Ereignis der Session
    erneuert (``app.database``) — ein Commit an der Session vorbei löst es nie
    aus; die Folgeabfrage lief ohne Kontext, RLS lieferte 0 Zeilen."""
    cr = ChangeRequest(
        tenant_id=TENANT_ID,
        user_id=user.id,
        request_type=ChangeRequestType.UPDATE,
        status=status,
        time_entry_id=entry.id,
        proposed_date=entry.date,
        proposed_start_time=prop_start,
        proposed_end_time=prop_end,
        proposed_break_minutes=prop_break,
        original_date=entry.date,
        original_start_time=entry.start_time,
        original_end_time=entry.end_time,
        original_break_minutes=entry.break_minutes,
        original_note=entry.note,
        original_uncredited_minutes=entry.uncredited_minutes,
        reason=reason,
        rejection_reason=rejection_reason,
        request_credit_override=request_credit_override,
    )
    if created_at is not None:
        # Realistischer Antragszeitpunkt statt der Seed-Uhr (sonst „gestellt“ und
        # „bearbeitet“ in derselben Minute des Stichtags).
        cr.created_at = created_at
        cr.updated_at = reviewed_at or created_at
    if status != ChangeRequestStatus.PENDING:
        cr.reviewed_by = reviewer.id if reviewer else None
        cr.reviewed_at = reviewed_at or datetime.now(timezone.utc)
    db.add(cr)


def _berlin(d: date, hour: int, minute: int) -> datetime:
    """Zeitpunkt ``d hour:minute`` Europe/Berlin als UTC-Datetime."""
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=BERLIN).astimezone(timezone.utc)


def _next_weekday(d: date) -> date:
    """Nächster Tag Mo–Fr nach ``d`` (Feiertage egal — nur für Antragszeitpunkte)."""
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def create_change_requests(db, users: list, stichtag: date, reviewer=None):
    """Maria: offener Antrag auf ihren letzten abgeschlossenen Eintrag vor dem
    Stichtag. Thomas: abgelehnter Antrag (Eintrag ≥ 14 Tage vor dem Stichtag,
    nie der §4-Befund). ``reviewer`` = die Verwalterin."""
    maria = next((u for u in users if u.username == "maria"), None)
    thomas = next((u for u in users if u.username == "thomas"), None)

    count = 0
    if maria:
        entry = db.query(TimeEntry).filter(
            TimeEntry.user_id == maria.id,
            TimeEntry.tenant_id == TENANT_ID,  # Superadmin-Kontext
            TimeEntry.date < stichtag,
            TimeEntry.end_time.isnot(None),
        ).order_by(TimeEntry.date.desc()).first()
        if entry:
            _add_change_request(
                db, maria, entry, ChangeRequestStatus.PENDING,
                dt_time(8, 0), dt_time(16, 45), 45,
                "Hatte vergessen, mich einzustempeln – tatsächliche Arbeitszeit war 8:00–16:45 Uhr.",
                # am Stichtag kurz nach dem Einstempeln (07:45) gestellt, vor der Aufnahme (10:30)
                created_at=_berlin(stichtag, 8, 5),
            )
            count += 1

    if thomas:
        entry = db.query(TimeEntry).filter(
            TimeEntry.user_id == thomas.id,
            TimeEntry.tenant_id == TENANT_ID,  # Superadmin-Kontext
            TimeEntry.date <= stichtag - timedelta(days=14),
            TimeEntry.break_waiver_reason.is_(None),
        ).order_by(TimeEntry.date.desc()).first()
        if entry:
            _add_change_request(
                db, thomas, entry, ChangeRequestStatus.REJECTED,
                dt_time(7, 30), dt_time(15, 30), 0,
                "Bitte Korrektur: Ich habe von 7:30 bis 15:30 Uhr durchgearbeitet, die Pause ist entfallen.",
                "Pausen-Nachweis fehlt. Gemäß ArbZG §4 sind bei >6h Arbeitszeit 30 Min. Pause vorgeschrieben.",
                reviewer=reviewer,
                # am Folgetag gestellt, am Tag danach abgelehnt — beides lange vor dem Stichtag
                created_at=_berlin(_next_weekday(entry.date), 7, 58),
                reviewed_at=_berlin(_next_weekday(_next_weekday(entry.date)), 9, 15),
            )
            count += 1

    # Sarah: „Anrechnung beantragen“ (P21) am ÄLTEREN über die Mittagslücke
    # durchgestempelten Tag — der neueste bleibt ohne Antrag (Aufnahme
    # ``ma-nicht-angerechnet``). Vorbelegt sind die Stempel, wie im Formular.
    sarah = next((u for u in users if u.username == "sarah"), None)
    if sarah:
        through = [
            e for e in db.query(TimeEntry).filter(
                TimeEntry.user_id == sarah.id,
                TimeEntry.tenant_id == TENANT_ID,  # Superadmin-Kontext
                TimeEntry.date < stichtag,
                TimeEntry.end_time.isnot(None),
                TimeEntry.uncredited_minutes > 0,
            ).order_by(TimeEntry.date.desc()).all()
        ]
        if len(through) >= 2:
            entry = through[1]
            _add_change_request(
                db, sarah, entry, ChangeRequestStatus.PENDING,
                entry.raw_start_time or entry.start_time, entry.raw_end_time or entry.end_time,
                entry.break_minutes,
                "Über Mittag habe ich Befunde für die Nachmittagssprechstunde vorbereitet – mit Dr. Werner abgesprochen.",
                created_at=_berlin(_next_weekday(entry.date), 7, 50),
                request_credit_override=True,
            )
            count += 1

    db.commit()
    print(f"  ✓ {count} Change Requests erstellt")


# ── Schichtplan ──────────────────────────────────────────────────────────────

def create_shift_plan(db, users: list, admin) -> None:
    """Ein heute gültiger Wochenplan wie über die Admin-Routen von
    ``routers/shift_planning.py`` angelegt: Arbeitsplätze (``create_workstation``),
    Plan (``create_plan`` + ``activate_plan``: ``is_active=True``), Schichten
    (``create_slot``) und Einteilungen (``set_assignments``), dazu Einweisungen
    (``set_user_qualifications``) für jeden eingeteilten Arbeitsplatz. Schreibt
    nur die Planungstabellen — nie Zeiteinträge, Abwesenheiten oder Salden."""
    by_name = {u.username: u for u in users}
    stations = {}
    for i, (name, color) in enumerate(SHIFT_WORKSTATIONS):
        ws = Workstation(tenant_id=TENANT_ID, name=name, color=color, sort_order=i)
        db.add(ws)
        stations[name] = ws
    db.flush()
    plan = ShiftPlan(
        tenant_id=TENANT_ID, name=SHIFT_PLAN_NAME, description=SHIFT_PLAN_DESCRIPTION,
        is_active=True, visible_to_employees=False, created_by=admin.id,
    )
    db.add(plan)
    db.flush()
    qualified = set()
    n_slots = n_assign = 0
    for ws_name, weekday, start, end, min_staff, note, usernames in SHIFT_SLOTS:
        slot = ShiftSlot(
            tenant_id=TENANT_ID, shift_plan_id=plan.id, workstation_id=stations[ws_name].id,
            weekday=weekday, start_time=dt_time.fromisoformat(start), end_time=dt_time.fromisoformat(end),
            min_staff=min_staff, note=note,
        )
        db.add(slot)
        db.flush()
        n_slots += 1
        for username in usernames:
            user = by_name.get(username)
            if user is None:
                continue
            db.add(ShiftAssignment(tenant_id=TENANT_ID, shift_slot_id=slot.id, user_id=user.id))
            qualified.add((user.id, stations[ws_name].id))
            n_assign += 1
    for user_id, ws_id in sorted(qualified, key=str):
        db.add(WorkstationQualification(tenant_id=TENANT_ID, user_id=user_id, workstation_id=ws_id))
    db.commit()
    print(f"  ✓ Schichtplan „{SHIFT_PLAN_NAME}“: {len(stations)} Arbeitsplätze, {n_slots} Schichten, {n_assign} Einteilungen")


# ── Ablauf ────────────────────────────────────────────────────────────────────

def seed_all(db, stichtag: date) -> None:
    start = data_start(stichtag)
    horizon = stichtag + timedelta(days=70)

    print("\n1. Admin aktualisieren...")
    admin = update_admin_password(db)

    print("\n2. Feiertage laden...")
    holiday_dates = get_holiday_dates(db, start - timedelta(days=7), horizon)
    print(f"  ✓ {len(holiday_dates)} Feiertage im Zeitraum")

    print("\n3. Mitarbeiter anlegen...")
    users = create_employees(db)

    print("\n4. Vertragsverlauf...")
    create_contract_history(db, users, stichtag)

    print("\n5. Einstellungen, Abwesenheitsgrund, verkürzter Tag...")
    create_settings_and_catalog(db, admin, stichtag, holiday_dates)

    print("\n6. Abwesenheiten, Betriebsferien, Urlaubsantrag...")
    create_absences(db, users, admin, stichtag, holiday_dates)

    print("\n7. Zeiteinträge...")
    for u in users:
        print(f"  [{u.first_name} {u.last_name}]")
        create_time_entries_for_user(db, u, holiday_dates, start, stichtag, stichtag=stichtag)

    print("\n8. Korrekturanträge...")
    create_change_requests(db, users, stichtag, reviewer=admin)

    print("\n9. Schichtplan...")
    create_shift_plan(db, users, admin)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Handbuch-Demodaten relativ zu einem Stichtag")
    parser.add_argument("--stichtag", help="YYYY-MM-DD (Standard: Mittwoch der Woche vor 14 Tagen)")
    parser.add_argument("--print-stichtag", action="store_true",
                        help="nur den Stichtag berechnen und als STICHTAG=... ausgeben (schreibt nichts außer fehlenden Feiertagen)")
    args = parser.parse_args(argv)

    db = SessionLocal()
    # Superadmin-Kontext: INSERTs in mandantengebundene Tabellen ohne RLS-Hürde.
    set_superadmin_context(db)
    try:
        if args.stichtag:
            stichtag = date.fromisoformat(args.stichtag)
            ensure_holidays(db, data_start(stichtag), stichtag + timedelta(days=80))
        else:
            today = date.today()
            ensure_holidays(db, today - timedelta(days=100), today + timedelta(days=60))
            around = get_holiday_dates(db, today - timedelta(days=30), today)
            stichtag = default_stichtag(today, around)
            ensure_holidays(db, data_start(stichtag), stichtag + timedelta(days=80))

        if args.print_stichtag:
            print(f"STICHTAG={stichtag}")
            return
        print("=" * 60)
        print("PraxisZeit – Handbuch-Testdaten (Praxis am Lindenplatz)")
        print(f"Stichtag: {stichtag}  Zeitraum: {data_start(stichtag)} bis {stichtag}")
        print("=" * 60)
        seed_all(db, stichtag)
        print("\n" + "=" * 60)
        print("Zugangsdaten (alle Konten): " + PASSWORD)
        print("  admin | maria | sarah | thomas | petra | julia")
        print("=" * 60)
    finally:
        db.close()
    print(f"STICHTAG={stichtag}")


if __name__ == "__main__":
    main()
