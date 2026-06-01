"""Urlaubskonto für Benutzer OHNE Stundenzählung (track_hours=False).

Hintergrund (Feedback / leitende Angestellte): Ein leitender Angestellter wird
modelliert als ``track_hours=False`` — keine Soll/Ist-Stundenzählung, sonst wie
ein normaler MA. Urlaub und Krank sollen trotzdem zählen, intern als REINE
TAGESZÄHLUNG (Stunden bleiben 0).

Bisher (F-046) lieferte ``get_vacation_account`` für diese User ein
„nicht anwendbar"-Konto: ``used_days=0`` / ``remaining_days=voller Anspruch``
unabhängig von tatsächlich gebuchtem Urlaub → der tagebasierte Budget-Check in
den Routern lief ins Leere (Über-Buchung möglich), und das Konto war faktisch
funktionslos.

Neu: Auch bei daily_target == 0 wird der Verbrauch tagebasiert gezählt
(1 VACATION-Tag = 1 Urlaubstag), während alle Stunden-Felder 0 bleiben.
Budget (budget_days) folgt weiterhin der normalen Logik inkl. Pro-rata und
Carryover ("sonst ändert sich nichts zu normalen MA").
"""

from datetime import date

import pytest

from app.models import User, UserRole, Absence, AbsenceType, YearCarryover
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _make_user(db, username="ltd", **kwargs):
    defaults = dict(
        email=f"{username}@example.com",
        password_hash="hash",
        first_name="Lea",
        last_name="Tend",
        role=UserRole.EMPLOYEE,
        weekly_hours=40.0,
        vacation_days=30,
        work_days_per_week=5,
        track_hours=False,  # leitende/r Angestellte/r: keine Stundenzählung
        is_active=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    defaults.update(kwargs)
    user = User(username=username, **defaults)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_absence(db, user, d, absence_type, hours=0.0):
    absence = Absence(
        user_id=user.id,
        tenant_id=DEFAULT_TENANT_ID,
        date=d,
        type=absence_type,
        hours=hours,
    )
    db.add(absence)
    db.commit()
    return absence


class TestUntrackedVacationAccount:
    def test_single_vacation_day_deducts_one_day_hours_zero(self, db, default_tenant):
        """1 Urlaubstag → used_days=1, remaining_days=29; alle Stunden bleiben 0."""
        u = _make_user(db)
        _make_absence(db, u, date(2026, 3, 10), AbsenceType.VACATION, 0.0)

        acc = calculation_service.get_vacation_account(db, u, 2026)
        assert acc["used_days"] == 1.0
        assert acc["remaining_days"] == 29.0
        assert acc["budget_days"] == 30.0
        # Stunden bleiben 0 (reine Tageszählung).
        assert acc["budget_hours"] == 0.0
        assert acc["used_hours"] == 0.0
        assert acc["remaining_hours"] == 0.0

    def test_multiple_vacation_days(self, db, default_tenant):
        """3 Urlaubstage → used_days=3, remaining_days=27."""
        u = _make_user(db)
        for d in (date(2026, 3, 10), date(2026, 3, 11), date(2026, 3, 12)):
            _make_absence(db, u, d, AbsenceType.VACATION, 0.0)

        acc = calculation_service.get_vacation_account(db, u, 2026)
        assert acc["used_days"] == 3.0
        assert acc["remaining_days"] == 27.0

    def test_sick_does_not_deduct_vacation(self, db, default_tenant):
        """Krank zählt NICHT gegen das Urlaubsbudget (nur VACATION wird gezählt)."""
        u = _make_user(db)
        _make_absence(db, u, date(2026, 3, 10), AbsenceType.SICK, 0.0)
        _make_absence(db, u, date(2026, 3, 11), AbsenceType.PAID_LEAVE, 0.0)

        acc = calculation_service.get_vacation_account(db, u, 2026)
        assert acc["used_days"] == 0.0
        assert acc["remaining_days"] == 30.0

    def test_budget_includes_carryover(self, db, default_tenant):
        """Budget folgt normaler Logik inkl. Urlaubsübertrag (sonst wie normale MA)."""
        u = _make_user(db)
        db.add(YearCarryover(
            user_id=u.id, tenant_id=DEFAULT_TENANT_ID,
            year=2026, overtime_hours=0, vacation_days=5.0,
        ))
        db.commit()

        acc = calculation_service.get_vacation_account(db, u, 2026)
        assert acc["budget_days"] == 35.0
        assert acc["remaining_days"] == 35.0

    def test_budget_prorated_for_mid_year_hire(self, db, default_tenant):
        """Pro-rata bei unterjährigem Eintritt gilt auch ohne Stundenzählung."""
        u = _make_user(db, username="midyear", vacation_days=24,
                        first_work_day=date(2026, 7, 1))
        acc = calculation_service.get_vacation_account(db, u, 2026)
        assert acc["budget_days"] == 12.0  # 24 × 6/12

    def test_remaining_drops_below_zero_is_visible(self, db, default_tenant):
        """Über-Buchung wird sichtbar (remaining_days < 0) statt still verschluckt.

        Das war der F-046-Kern: vorher meldete das Konto trotz gebuchten Urlaubs
        immer den vollen Rest, sodass der tagebasierte Budget-Check nie griff.
        """
        u = _make_user(db, vacation_days=2)
        for d in (date(2026, 3, 9), date(2026, 3, 10), date(2026, 3, 11)):
            _make_absence(db, u, d, AbsenceType.VACATION, 0.0)

        acc = calculation_service.get_vacation_account(db, u, 2026)
        assert acc["used_days"] == 3.0
        assert acc["remaining_days"] == -1.0

    def test_sentinel_track_hours_stays_false(self, db, default_tenant):
        """Das track_hours-Sentinel bleibt False (UI blendet Stundenspalten aus)."""
        u = _make_user(db)
        acc = calculation_service.get_vacation_account(db, u, 2026)
        assert acc["track_hours"] is False
