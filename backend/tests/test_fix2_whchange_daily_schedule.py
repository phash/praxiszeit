"""Fix #2 — der Vorfall und seine Auflösung durch #431.

Vorfall: eine WorkingHoursChange war für use_daily_schedule-MA wirkungslos
(get_daily_target_for_date las dann nur hours_mon…fri, NICHT weekly_hours) →
die Stunden-Historie hätte null Effekt aufs Soll gehabt, die UI zeigte aber den
neuen Wert (stille falsche §16-Records). Die damalige Entscheidung: solche
Anträge mit HTTP 400 ablehnen, statt eine wirkungslose Historie zu schreiben.

Auflösung (#431): die Historien-Zeile trägt jetzt den VOLLSTÄNDIGEN
Vertrags-Snapshot (Modus + Tageswerte + Arbeitstage + Wochenstunden) und
get_daily_target_for_date rechnet gegen den datumsaufgelösten Snapshot — die
Zeile ist für diese Gruppe nicht mehr wirkungslos. Damit ist die Begründung der
Sperre weg und sie entfällt. Der Test kehrt die Erwartung um und prüft genau
das, was die Sperre verhindern sollte: dass die Zeile das Soll des
Tagesplan-Mitarbeitenden tatsächlich verschiebt.
"""
from datetime import date, timedelta
from decimal import Decimal

from app.models import User, UserRole, WorkingHoursChange
from app.routers.admin_users import create_working_hours_change
from app.schemas.working_hours_change import WorkingHoursChangeCreate
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _make_user(db, username, **kwargs):
    defaults = dict(
        email=f"{username}@x.de", password_hash="h", first_name=username,
        last_name="T", role=UserRole.EMPLOYEE, weekly_hours=40.0, vacation_days=30,
        work_days_per_week=5, is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kwargs)
    u = User(username=username, **defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _admin(db):
    return _make_user(db, "wh_admin", role=UserRole.ADMIN)


def test_whchange_accepted_for_daily_schedule_user(db, default_tenant):
    """use_daily_schedule=True → 201 mit vollständigem Snapshot in der Zeile.

    Die Zeile darf nicht mehr `use_daily_schedule=False` (Column-Default) und
    `work_days_per_week=NULL` tragen — das kippte den Mitarbeitenden ab ihrem
    Wirkungsdatum still in den Wochenstunden-Modus.
    """
    admin = _admin(db)
    emp = _make_user(
        db, "wh_daily", use_daily_schedule=True,
        hours_monday=8.0, hours_tuesday=8.0, hours_wednesday=8.0,
        hours_thursday=8.0, hours_friday=8.0,
    )
    result = create_working_hours_change(
        user_id=str(emp.id),
        change_data=WorkingHoursChangeCreate(
            effective_from=date(2026, 1, 1),
            use_daily_schedule=True,
            hours_monday=4.0, hours_tuesday=4.0, hours_wednesday=4.0,
            hours_thursday=4.0, hours_friday=4.0,
            work_days_per_week=5,
        ),
        db=db, current_user=admin,
    )

    assert result.use_daily_schedule is True
    assert Decimal(str(result.hours_monday)) == Decimal("4.00")
    assert result.work_days_per_week == 5
    # Wochenstunden serverseitig als Summe der Tageswerte.
    assert float(result.weekly_hours) == 20.0

    rows = (
        db.query(WorkingHoursChange)
        .filter(WorkingHoursChange.user_id == emp.id)
        .order_by(WorkingHoursChange.effective_from)
        .all()
    )
    assert len(rows) == 2, "Basis-Zeile friert den bisherigen Tagesplan ein"
    assert rows[0].use_daily_schedule is True
    assert Decimal(str(rows[0].hours_monday)) == Decimal("8.00")


def test_whchange_actually_shifts_the_daily_schedule_target(db, default_tenant):
    """Der Kern des Vorfalls: die Zeile war fürs Soll WIRKUNGSLOS. Genau das
    muss jetzt nachweislich anders sein — vor dem Wirkungsdatum 8 h/Tag, ab dem
    Wirkungsdatum 4 h/Tag."""
    admin = _admin(db)
    emp = _make_user(
        db, "wh_daily_target", use_daily_schedule=True,
        hours_monday=8.0, hours_tuesday=8.0, hours_wednesday=8.0,
        hours_thursday=8.0, hours_friday=8.0,
        # Ohne Eintrittsdatum deckte die Basis-Zeile nur den Vortag ab; ein
        # Stichtag davor fiele auf die (vom Resync bereits überschriebenen)
        # User-Felder zurück und wir prüften nichts.
        first_work_day=date(2025, 1, 1),
    )
    eff = date(2026, 1, 5)  # ein Montag
    create_working_hours_change(
        user_id=str(emp.id),
        change_data=WorkingHoursChangeCreate(
            effective_from=eff,
            use_daily_schedule=True,
            hours_monday=4.0, hours_tuesday=4.0, hours_wednesday=4.0,
            hours_thursday=4.0, hours_friday=4.0,
            work_days_per_week=5,
        ),
        db=db, current_user=admin,
    )

    db.expire_all()
    emp = db.query(User).filter(User.id == emp.id).first()
    before = eff - timedelta(days=7)
    assert calculation_service.get_daily_target_for_date(
        emp, before, calculation_service.get_schedule_for_date(db, emp, before),
    ) == Decimal("8.00")
    assert calculation_service.get_daily_target_for_date(
        emp, eff, calculation_service.get_schedule_for_date(db, emp, eff),
    ) == Decimal("4.00")


def test_whchange_ok_for_normal_user(db, default_tenant):
    """Normaler MA (use_daily_schedule=False) → unverändert ok, Zeile angelegt."""
    admin = _admin(db)
    emp = _make_user(db, "wh_normal")  # use_daily_schedule default False
    result = create_working_hours_change(
        user_id=str(emp.id),
        change_data=WorkingHoursChangeCreate(
            effective_from=date(2026, 1, 1), weekly_hours=20.0,
        ),
        db=db, current_user=admin,
    )
    assert float(result.weekly_hours) == 20.0
    # Release-Review 1.16.0: die ERSTE Änderung legt zusätzlich eine Basis-Zeile mit
    # dem bisherigen Vertragswert an. Ohne sie fiele `get_weekly_hours_for_date` für
    # die gesamte Vergangenheit auf `user.weekly_hours` zurück — das gerade auf den
    # NEUEN Wert gesetzt wird —, wodurch sich das Soll bereits abgeschlossener
    # Monate rückwirkend verschoben hätte.
    rows = (
        db.query(WorkingHoursChange)
        .filter(WorkingHoursChange.user_id == emp.id)
        .order_by(WorkingHoursChange.effective_from)
        .all()
    )
    assert len(rows) == 2
    assert float(rows[0].weekly_hours) == 40.0, "Ausgangswert eingefroren"
    assert rows[0].effective_from < date(2026, 1, 1)
    assert float(rows[1].weekly_hours) == 20.0


# ---------------------------------------------------------------------------
# Finding 4 (HIGH, Review 2026-07-14): die Session ist autoflush=False. Ohne ein
# db.flush() nach db.add(change) UND VOR der Most-Recent-Selbstabfrage sieht
# diese Abfrage die gerade hinzugefügte Zeile nicht → user.weekly_hours bleibt
# beim ersten rückwirkenden Antrag unverändert bzw. übernimmt bei einer
# zweiten, überholenden Änderung den VORHERIGEN statt den neuen Wert.
# ---------------------------------------------------------------------------

def test_whchange_first_past_dated_change_updates_weekly_hours(db, default_tenant):
    """Die allererste rückwirkende (effective_from <= heute) Stundenänderung muss
    user.weekly_hours SOFORT auf den neuen Wert setzen."""
    admin = _admin(db)
    emp = _make_user(db, "wh_first", weekly_hours=40.0)
    result = create_working_hours_change(
        user_id=str(emp.id),
        change_data=WorkingHoursChangeCreate(
            effective_from=date(2020, 1, 1), weekly_hours=20.0,
        ),
        db=db, current_user=admin,
    )
    assert float(result.weekly_hours) == 20.0
    assert float(emp.weekly_hours) == 20.0


def test_whchange_second_superseding_change_updates_to_new_value(db, default_tenant):
    """Eine zweite, spätere rückwirkende Änderung muss user.weekly_hours auf
    IHREN Wert setzen — nicht auf den der ersten (bereits committeten) Änderung."""
    admin = _admin(db)
    emp = _make_user(db, "wh_second", weekly_hours=40.0)
    create_working_hours_change(
        user_id=str(emp.id),
        change_data=WorkingHoursChangeCreate(
            effective_from=date(2020, 1, 1), weekly_hours=20.0,
        ),
        db=db, current_user=admin,
    )
    result = create_working_hours_change(
        user_id=str(emp.id),
        change_data=WorkingHoursChangeCreate(
            effective_from=date(2020, 6, 1), weekly_hours=30.0,
        ),
        db=db, current_user=admin,
    )
    assert float(result.weekly_hours) == 30.0
    assert float(emp.weekly_hours) == 30.0
