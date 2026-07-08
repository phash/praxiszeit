"""#377 Mindestlohn-Konstante + /api/system/info-Ausgabe."""
from datetime import date
from decimal import Decimal

from app.core import minimum_wage as mw


def test_minimum_wage_for_boundaries():
    assert mw.minimum_wage_for(date(2025, 12, 31)) == Decimal("12.82")
    assert mw.minimum_wage_for(date(2026, 1, 1)) == Decimal("13.90")
    assert mw.minimum_wage_for(date(2026, 7, 8)) == Decimal("13.90")
    assert mw.minimum_wage_for(date(2027, 1, 1)) == Decimal("14.60")
    assert mw.minimum_wage_for(date(2030, 1, 1)) == Decimal("14.60")  # letzte Stufe hält


def test_minimum_wage_info_current_and_next():
    info = mw.minimum_wage_info(date(2026, 7, 8))
    assert info["current"] == 13.90
    assert info["since"] == "2026-01-01"
    assert info["next"] == {"value": 14.60, "from": "2027-01-01"}
    # nach der letzten Stufe kein next mehr
    assert mw.minimum_wage_info(date(2027, 6, 1))["next"] is None
    # vor 2026: current 12,82, next 13,90
    early = mw.minimum_wage_info(date(2025, 6, 1))
    assert early["current"] == 12.82 and early["next"]["value"] == 13.90


def test_system_info_exposes_minimum_wage():
    from fastapi.testclient import TestClient
    from app.main import app
    body = TestClient(app).get("/api/system/info").json()
    assert "minimum_wage" in body
    assert body["minimum_wage"]["current"] > 0
    assert "since" in body["minimum_wage"] and "next" in body["minimum_wage"]
