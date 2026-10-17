"""Gesamtreview 1.20: eigene Feiertage in einem abgeschlossenen Jahr melden
den veralteten Übertrag (Fix #5), wie seit B9 der Bundesland-Wechsel.

Anlegen, Verschieben und Löschen eines eigenen Feiertags ändern Soll und
Gutschrift des Datums (``_day_soll_contribution`` / ``credit_day_weight``).
Ist das Jahr bereits abgeschlossen (``YearCarryover`` für Y+1 vorhanden),
liefert der Endpunkt eine ``warning`` — neu gerechnet wird nichts.
"""

from datetime import date

from app.models.public_holiday import PublicHoliday
from app.models.year_carryover import YearCarryover
from tests.test_custom_holidays import (  # noqa: F401 — Fixtures
    TENANT_A_ID,
    _db_session,
    admin_a,
    client_as_admin_a,
    two_tenants,
)


def _close_year(db, user, year):
    db.add(YearCarryover(
        tenant_id=TENANT_A_ID, user_id=user.id, year=year + 1,
        overtime_hours=0, vacation_days=0,
    ))
    db.commit()


def _custom(db, d):
    h = PublicHoliday(
        date=d, name="Schützenfest", year=d.year,
        tenant_id=TENANT_A_ID, is_custom=True, source="admin",
    )
    db.add(h)
    db.commit()
    return str(h.id)


def test_create_in_closed_year_warns(_db_session, admin_a, client_as_admin_a):
    _close_year(_db_session, admin_a, 2025)
    resp = client_as_admin_a.post(
        "/api/holidays/", json={"name": "Schützenfest", "date": "2025-08-15"}
    )
    assert resp.status_code == 201, resp.text
    assert "Jahresabschluss 2025" in (resp.json().get("warning") or "")


def test_create_in_open_year_has_no_warning(_db_session, admin_a, client_as_admin_a):
    _close_year(_db_session, admin_a, 2025)
    resp = client_as_admin_a.post(
        "/api/holidays/", json={"name": "Schützenfest", "date": "2026-08-14"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json().get("warning") is None


def test_move_out_of_closed_year_warns(_db_session, admin_a, client_as_admin_a):
    _close_year(_db_session, admin_a, 2025)
    hid = _custom(_db_session, date(2025, 8, 15))
    resp = client_as_admin_a.put(f"/api/holidays/{hid}", json={"date": "2026-08-14"})
    assert resp.status_code == 200, resp.text
    assert "Jahresabschluss 2025" in (resp.json().get("warning") or "")


def test_move_into_closed_year_warns(_db_session, admin_a, client_as_admin_a):
    _close_year(_db_session, admin_a, 2025)
    hid = _custom(_db_session, date(2026, 8, 14))
    resp = client_as_admin_a.put(f"/api/holidays/{hid}", json={"date": "2025-08-15"})
    assert resp.status_code == 200, resp.text
    assert "Jahresabschluss 2025" in (resp.json().get("warning") or "")


def test_rename_in_closed_year_stays_silent(_db_session, admin_a, client_as_admin_a):
    """Nur der Name ändert sich → Soll und Saldo unberührt, kein Hinweis."""
    _close_year(_db_session, admin_a, 2025)
    hid = _custom(_db_session, date(2025, 8, 15))
    resp = client_as_admin_a.put(
        f"/api/holidays/{hid}", json={"name": "Umbenannt", "date": "2025-08-15"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("warning") is None


def test_delete_in_closed_year_warns_with_200(_db_session, admin_a, client_as_admin_a):
    _close_year(_db_session, admin_a, 2025)
    hid = _custom(_db_session, date(2025, 8, 15))
    resp = client_as_admin_a.delete(f"/api/holidays/{hid}")
    assert resp.status_code == 200, resp.text
    assert "Jahresabschluss 2025" in resp.json()["warning"]


def test_delete_in_open_year_stays_204(_db_session, admin_a, client_as_admin_a):
    _close_year(_db_session, admin_a, 2025)
    hid = _custom(_db_session, date(2026, 8, 14))
    resp = client_as_admin_a.delete(f"/api/holidays/{hid}")
    assert resp.status_code == 204, resp.text


def test_other_tenants_closing_does_not_warn(_db_session, admin_a, client_as_admin_a):
    """F-026: ein Jahresabschluss eines fremden Mandanten zählt nicht."""
    from tests.test_custom_holidays import TENANT_B_ID, _make_admin
    other = _make_admin(_db_session, TENANT_B_ID, "admin_b_gr")
    _db_session.add(YearCarryover(
        tenant_id=TENANT_B_ID, user_id=other.id, year=2026,
        overtime_hours=0, vacation_days=0,
    ))
    _db_session.commit()
    resp = client_as_admin_a.post(
        "/api/holidays/", json={"name": "Schützenfest", "date": "2025-08-15"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json().get("warning") is None
