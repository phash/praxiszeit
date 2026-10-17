"""Ultrareview 1.20 (Fund 3): die Urlaubsbudget-Vorprüfung mit Zeitraum lebt an
EINER Stelle (``admin_helpers.ensure_vacation_budget``) — vorher viermal
ausgeschrieben (Direktbuchung, Antrag anlegen, Antrag bearbeiten,
Antrags-Genehmigung), mit Drift-Risiko bei jeder Regeländerung."""
import inspect
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.routers import absences, admin_helpers, admin_vacations, vacation_requests
from app.services import calculation_service


def test_message_and_status_are_unchanged(monkeypatch):
    monkeypatch.setattr(calculation_service, "vacation_day_cost_by_year",
                        lambda *a, **k: {2026: Decimal("3")})
    monkeypatch.setattr(calculation_service, "vacation_budget_shortfall",
                        lambda *a, **k: (2026, 2.0))
    with pytest.raises(HTTPException) as exc:
        admin_helpers.ensure_vacation_budget(None, None, [date(2026, 3, 2)], False)
    assert (exc.value.status_code, exc.value.detail) == (
        400, "Nicht genügend Urlaubstage für 2026 (2.0 Tage verfügbar)")


def test_no_shortfall_passes_and_forwards_the_arguments(monkeypatch):
    seen = {}

    def _cost(db, user, dates, half_day, wh_changes=None, year_cache=None):
        seen["cost"] = (dates, half_day, wh_changes, year_cache)
        return {2026: Decimal("0.5")}

    def _short(db, user, cost_by_year, wh_changes=None):
        seen["short"] = (cost_by_year, wh_changes)
        return None

    monkeypatch.setattr(calculation_service, "vacation_day_cost_by_year", _cost)
    monkeypatch.setattr(calculation_service, "vacation_budget_shortfall", _short)
    cache: dict = {}
    admin_helpers.ensure_vacation_budget(None, None, ["d"], True, wh_changes=["w"],
                                         year_cache=cache)
    assert seen == {"cost": (["d"], True, ["w"], cache),
                    "short": ({2026: Decimal("0.5")}, ["w"])}


@pytest.mark.parametrize("module", [absences, admin_vacations, vacation_requests])
def test_routers_use_the_shared_helper(module):
    src = inspect.getsource(module)
    assert "ensure_vacation_budget(" in src
    assert "Nicht genügend Urlaubstage" not in src
    assert "vacation_budget_shortfall" not in src
