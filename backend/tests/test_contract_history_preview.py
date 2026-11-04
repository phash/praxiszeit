"""Teil A, Task 7: beide Vorschauen zeigen den Urlaubsanspruch bisher → neu
(Jahr des Wirkungsdatums und Folgejahr); eine RÜCKWIRKENDE Senkung ist der
Verkürzungsgrund ``vacation_entitlement``; die Sammelzeile nennt geänderte
Vertragsbedingungen (``reclamp_audit.contract_pair``)."""
from datetime import date
from decimal import Decimal

import pytest

from app.models import YearCarryover
from app.services import reclamp_audit
from tests.conftest import DEFAULT_TENANT_ID
from tests.wh_change_helpers import (
    contract_client_fixture, changes_url as url, rows_of, add_row, explicit_contract, reclamp_logs,
)

client = pytest.fixture(name="client")(contract_client_fixture)

BASE = date(2020, 1, 1)


def body(eff: str, **extra) -> dict:
    return {"effective_from": eff, "weekly_hours": 40, "work_days_per_week": 5, **extra}


def _customer(db, user):
    """Spec A5 Kundenfall: keine Zeilen, 40 h an 4 Tagen, Anspruch 24."""
    user.vacation_days = 24
    user.weekly_hours = 40
    user.work_days_per_week = 4
    user.use_daily_schedule = False
    db.commit()


def _baseline(db, user, vacation=24):
    """Person mit Anspruch ``vacation`` seit 2020 (Basiszeile), 40 h an 5 Tagen."""
    return add_row(db, user, BASE, weekly_hours=40, **explicit_contract(vacation_days=Decimal(str(vacation))))


def summary_row(db, user):
    return reclamp_logs(db, user, summary=True)[-1]


def test_preview_shows_entitlement_for_year_and_next(db, test_user, client):
    _customer(db, test_user)
    r = client.post(url(test_user) + "/preview", json=body("2026-11-01", vacation_days=30))
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["vacation_entitlement"] == [{"year": 2026, "before": 24.0, "after": 25.0},
                                         {"year": 2027, "before": 24.0, "after": 30.0}]
    assert p["is_shortening"] is False
    assert rows_of(db, test_user) == []                     # Vorschau schreibt nie


def test_preview_unchanged_snapshot_shows_entitlement_unchanged(db, test_user, client):
    _customer(db, test_user)
    p = client.post(url(test_user) + "/preview", json=body("2026-11-01", work_days_per_week=4)).json()
    assert p["vacation_entitlement"] == [{"year": 2026, "before": 24.0, "after": 24.0},
                                         {"year": 2027, "before": 24.0, "after": 24.0}]


def test_delete_preview_shows_entitlement_back(db, test_user, client):
    _customer(db, test_user)
    r = client.post(url(test_user), json=body("2026-11-01", vacation_days=30))
    assert r.status_code == 201, r.text
    change_id = r.json()["id"]
    d = client.post(f"{url(test_user)}/{change_id}/delete-preview", json={})
    assert d.status_code == 200, d.text
    assert d.json()["vacation_entitlement"] == [{"year": 2026, "before": 25.0, "after": 24.0},
                                                {"year": 2027, "before": 30.0, "after": 24.0}]
    assert len(rows_of(db, test_user)) == 2                 # Vorschau löscht nie
    # F032: das Löschen einer RÜCKWIRKENDEN Erhöhung senkt den Anspruch → Verkürzung.
    assert d.json()["is_shortening"] is True
    assert "vacation_entitlement" in d.json()["shortening_reasons"]
    # Ohne Grund 400, Zeile und users.vacation_days bleiben.
    refused = client.request("DELETE", f"{url(test_user)}/{change_id}")
    assert refused.status_code == 400, refused.text
    assert len(rows_of(db, test_user)) == 2
    db.expire_all()
    assert test_user.vacation_days == 30
    # Mit Grund geht das Löschen durch.
    ok = client.request("DELETE", f"{url(test_user)}/{change_id}", json={
        "retroactive_reason_type": "erfassungsfehler", "retroactive_reason_text": "Anspruch war falsch erfasst",
        "wage_risk_confirmed": True})
    assert ok.status_code in (200, 204), ok.text
    assert len(rows_of(db, test_user)) == 1


def test_retroactive_entitlement_decrease_is_shortening(db, test_user, client):
    _baseline(db, test_user)
    p = client.post(url(test_user) + "/preview", json=body("2026-10-01", vacation_days=20)).json()
    # 2026: 24 × 9/12 + 20 × 3/12 = 18 + 5 = 23
    assert p["vacation_entitlement"][0] == {"year": 2026, "before": 24.0, "after": 23.0}
    assert "vacation_entitlement" in p["shortening_reasons"]
    assert p["is_shortening"] is True
    r = client.post(url(test_user), json=body("2026-10-01", vacation_days=20))
    assert r.status_code == 400, r.text
    assert "Urlaubsanspruch 2026 24 → 23 Tage" in r.json()["detail"]
    assert len(rows_of(db, test_user)) == 1                 # nichts gespeichert
    ok = client.post(url(test_user), json=body(
        "2026-10-01", vacation_days=20, retroactive_reason_type="einvernehmlich",
        retroactive_reason_text="Reduzierung vereinbart", wage_risk_confirmed=True))
    assert ok.status_code == 201, ok.text
    parsed = reclamp_audit.parse_summary_note(summary_row(db, test_user).new_note)
    assert parsed.shortening is True and parsed.reason_type == "einvernehmlich"


def test_decrease_from_today_or_future_is_not_shortening(db, test_user, client):
    _baseline(db, test_user)
    for eff in ("2026-11-03", "2027-01-01"):
        p = client.post(url(test_user) + "/preview", json=body(eff, vacation_days=20)).json()
        assert "vacation_entitlement" not in p["shortening_reasons"], eff
        assert p["is_shortening"] is False, eff
        assert any(e["after"] < e["before"] for e in p["vacation_entitlement"]), eff
    r = client.post(url(test_user), json=body("2026-11-03", vacation_days=20))
    assert r.status_code == 201, r.text


def test_summary_row_names_changed_contract_terms(db, test_user, client):
    _customer(db, test_user)
    r = client.post(url(test_user), json=body("2026-11-01", vacation_days=30))
    assert r.status_code == 201, r.text
    note = summary_row(db, test_user).new_note
    assert note.endswith("Vertrag: 40,0 h/Woche (gleichmäßig, 4 Tage) · Urlaub 24 → "
                         "40,0 h/Woche (gleichmäßig, 5 Tage) · Urlaub 30")
    parsed = reclamp_audit.parse_summary_note(note)
    assert parsed is not None and parsed.effective_from == date(2026, 11, 1) and parsed.shortening is False


def test_hours_only_change_summary_text_unchanged(db, test_user, client):
    _customer(db, test_user)
    r = client.post(url(test_user), json=body("2026-11-01", weekly_hours=38, work_days_per_week=4))
    assert r.status_code == 201, r.text
    note = summary_row(db, test_user).new_note
    assert note.endswith("Vertrag: 40,0 h/Woche (gleichmäßig, 4 Tage) → 38,0 h/Woche (gleichmäßig, 4 Tage)")
    assert " · Urlaub" not in note


def test_entitlement_change_in_closed_year_warns_and_recalculates_nothing(db, test_user, client):
    _baseline(db, test_user)
    carry = YearCarryover(tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id, year=2026,
                          overtime_hours=Decimal("3.5"), vacation_days=Decimal("4.5"), source="year_closing")
    db.add(carry)
    db.commit()
    r = client.post(url(test_user), json=body(
        "2025-06-01", vacation_days=30, retroactive_reason_type="erfassungsfehler",
        retroactive_reason_text="Anspruch falsch erfasst", wage_risk_confirmed=True))
    assert r.status_code == 201, r.text
    assert r.json()["warning"]
    assert "2025" in r.json()["warning"]
    db.expire_all()
    carry = db.get(YearCarryover, carry.id)
    assert carry.vacation_days == Decimal("4.5") and carry.overtime_hours == Decimal("3.5")
