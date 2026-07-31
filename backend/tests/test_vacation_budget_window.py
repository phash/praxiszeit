"""Fix #1: vacation budget for years ENTIRELY outside the employment window.

The pro-rata branches in ``get_vacation_account`` only handle the entry/exit
*year*. A year completely before ``first_work_day`` (future hire) or completely
after ``last_work_day`` (departed employee) had no ``else`` branch, so it kept
the full ``vacation_days`` budget (+ carryover) → phantom entitlement that even
fed the carryover. Such years must grant zero budget.

Audit 2026-07-31 (Fund B) ergänzt die andere Hälfte derselben Funktion: der
VERBRAUCH muss dasselbe Fenster respektieren wie das Budget. Die vier Tests
oben legten keine einzige Urlaubs-Abwesenheit an — deshalb lief die
Verbrauchsschleife hier nie mit einem gesetzten Fenster.
"""
from datetime import date

from app.models import Absence, AbsenceType, User, UserRole, YearCarryover
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _mk(db, username, first_work_day=None, last_work_day=None, vacation_days=30,
        track_hours=True):
    u = User(
        username=username, email=f"{username}@x.de", password_hash="h",
        first_name=username, last_name="T", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=vacation_days, work_days_per_week=5,
        is_active=True, track_hours=track_hours, tenant_id=DEFAULT_TENANT_ID,
        first_work_day=first_work_day, last_work_day=last_work_day,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _vacation(db, user, *days, hours=8.0):
    for d in days:
        db.add(Absence(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, date=d,
                       type=AbsenceType.VACATION, hours=hours, half_day=False))
    db.commit()


# 01.-03.07.2026 = Mi-Fr, 06./07.07. = Mo/Di  →  fünf Werktage
JULY = [date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3),
        date(2026, 7, 6), date(2026, 7, 7)]
# 03.-07.08.2026 = Mo-Fr  →  fünf Werktage
AUGUST = [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5),
          date(2026, 8, 6), date(2026, 8, 7)]


def test_year_after_last_work_day_has_zero_budget(db, default_tenant):
    u = _mk(db, "leaver", last_work_day=date(2025, 6, 30))
    acc = calculation_service.get_vacation_account(db, u, 2026)  # year AFTER exit
    assert acc["budget_days"] == 0.0
    assert acc["remaining_days"] == 0.0


def test_year_before_first_work_day_has_zero_budget(db, default_tenant):
    u = _mk(db, "starter", first_work_day=date(2026, 9, 1))
    acc = calculation_service.get_vacation_account(db, u, 2025)  # year BEFORE entry
    assert acc["budget_days"] == 0.0
    assert acc["remaining_days"] == 0.0


def test_out_of_window_year_ignores_carryover(db, default_tenant):
    # Even a stray carryover row must not resurrect a budget for a year the
    # employee was not employed at all.
    u = _mk(db, "leaver2", last_work_day=date(2025, 6, 30))
    db.add(YearCarryover(user_id=u.id, tenant_id=DEFAULT_TENANT_ID, year=2026,
                         overtime_hours=0, vacation_days=10))
    db.commit()
    acc = calculation_service.get_vacation_account(db, u, 2026)
    assert acc["budget_days"] == 0.0
    assert acc["remaining_days"] == 0.0


def test_entry_year_still_pro_rata(db, default_tenant):
    # Guard must NOT affect the entry year itself (regression guard).
    u = _mk(db, "starter2", first_work_day=date(2026, 9, 1))
    acc = calculation_service.get_vacation_account(db, u, 2026)
    assert acc["budget_days"] == 10.0  # 30 * (Sep-Dec = 4 months) / 12


# ---------------------------------------------------------------------------
# Audit 2026-07-31 (Fund B): der VERBRAUCH muss dasselbe Fenster respektieren
# ---------------------------------------------------------------------------
# ``get_vacation_account`` wandte das Beschäftigungsfenster dreimal an (Budget-
# Pro-rata, freie Sondertage im tracked- und im untracked-Zweig) und einmal
# NICHT: auf der Schleife über die echten Urlaubszeilen. Erreichbar im
# Regelbetrieb — ``admin_users.update_user`` setzt ``last_work_day`` und räumt
# KEINE Abwesenheiten ab: im März Urlaub für Juli genehmigt, im Mai Kündigung
# zum 30.06. Der Wert ist die Grundlage der Urlaubsabgeltung (§ 7 Abs. 4 BUrlG,
# also Geld) und geht über den Jahresabschluss in den Übertrag.

def test_vacation_after_last_work_day_does_not_consume_budget(db, default_tenant):
    """Austritt 30.06., fünf Urlaubstage im Juli → sie zählen NICHT.

    Vorher: budget 15,0 / used 5,0 / remaining 10,0 — während
    ``get_monthly_target(2026, 7)`` für denselben Mitarbeiter korrekt 0 liefert.
    Der Resturlaub, der abzugelten ist, war um fünf Tage zu niedrig."""
    u = _mk(db, "leaver_vac", last_work_day=date(2026, 6, 30))
    _vacation(db, u, *JULY)

    acc = calculation_service.get_vacation_account(db, u, 2026)
    assert acc["budget_days"] == 15.0  # 30 × 6/12
    assert calculation_service.get_monthly_target(db, u, 2026, 7) == 0, \
        "Kontrolle: die Soll-Seite kennt das Fenster längst"
    assert acc["used_days"] == 0.0
    assert acc["used_hours"] == 0.0
    assert acc["remaining_days"] == 15.0


def test_vacation_before_first_work_day_does_not_consume_budget(db, default_tenant):
    """Spiegelfall: Eintritt 01.09., Urlaubszeilen im August."""
    u = _mk(db, "starter_vac", first_work_day=date(2026, 9, 1))
    _vacation(db, u, *AUGUST)

    acc = calculation_service.get_vacation_account(db, u, 2026)
    assert acc["budget_days"] == 10.0  # 30 × 4/12
    assert acc["used_days"] == 0.0
    assert acc["remaining_days"] == 10.0


def test_untracked_branch_also_respects_the_window(db, default_tenant):
    """#191 leitende Angestellte (``track_hours=False``): der reine
    Tageszähl-Zweig hatte dieselbe Lücke."""
    u = _mk(db, "leader_vac", last_work_day=date(2026, 6, 30), track_hours=False)
    _vacation(db, u, *JULY, hours=0.0)

    acc = calculation_service.get_vacation_account(db, u, 2026)
    assert acc["track_hours"] is False
    assert acc["budget_days"] == 15.0
    assert acc["used_days"] == 0.0
    assert acc["remaining_days"] == 15.0


def test_vacation_inside_the_window_still_counts(db, default_tenant):
    """Kontrolltest: der Fix darf NUR Zeilen ausserhalb des Fensters
    ausblenden. Dieselbe Konstellation mit Urlaub VOR dem Austritt zählt
    unverändert voll."""
    u = _mk(db, "leaver_inside", last_work_day=date(2026, 6, 30))
    # 01.-05.06.2026 = Mo-Fr, alle innerhalb des Fensters
    _vacation(db, u, date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3),
              date(2026, 6, 4), date(2026, 6, 5))

    acc = calculation_service.get_vacation_account(db, u, 2026)
    assert acc["budget_days"] == 15.0
    assert acc["used_days"] == 5.0
    assert acc["used_hours"] == 40.0
    assert acc["remaining_days"] == 10.0


def test_no_window_at_all_still_counts(db, default_tenant):
    """Kontrolltest: ohne gesetztes Fenster ändert sich nichts (der Regelfall)."""
    u = _mk(db, "no_window")
    _vacation(db, u, *JULY)

    acc = calculation_service.get_vacation_account(db, u, 2026)
    assert acc["budget_days"] == 30.0
    assert acc["used_days"] == 5.0
    assert acc["remaining_days"] == 25.0
