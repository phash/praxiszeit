"""Kundenfall 2026-11-02: Ein von Hand eingetragener Übertrag (Dialog
„Übernahme", ``source='manual'``) ist KEIN Jahresabschluss. Bisher machte ein
Resturlaub-Übertrag für 2027 bei irgendeiner Person das Jahr 2026 für den ganzen
Mandanten zum „abgeschlossenen Jahr" — mit Sperren und Warnungen, obwohl
niemand einen Jahresabschluss ausgeführt hatte."""
from decimal import Decimal

from app.models import YearCarryover
from app.services import calculation_service
from tests.conftest import DEFAULT_TENANT_ID


def _carry(db, user, year, source):
    db.add(YearCarryover(user_id=user.id, tenant_id=DEFAULT_TENANT_ID, year=year,
                         overtime_hours=Decimal("0"), vacation_days=Decimal("2"), source=source))
    db.commit()


def test_manual_carryover_does_not_close_the_year(db, test_user):
    _carry(db, test_user, 2027, "manual")
    assert calculation_service.closed_years_in_range(db, DEFAULT_TENANT_ID, [2026]) == []
    assert calculation_service.all_closed_years(db, DEFAULT_TENANT_ID) == []
    assert calculation_service.stale_year_closing_warning(db, DEFAULT_TENANT_ID, [2026]) is None


def test_year_closing_carryover_closes_the_year(db, test_user):
    _carry(db, test_user, 2027, "year_closing")
    assert calculation_service.closed_years_in_range(db, DEFAULT_TENANT_ID, [2026]) == [2026]
    assert calculation_service.all_closed_years(db, DEFAULT_TENANT_ID) == [2026]
