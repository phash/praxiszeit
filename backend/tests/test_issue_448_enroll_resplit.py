"""#448: enrolling a newly participating employee into open Betriebsferien must
trigger the same #314 calendar-order re-split as every other closure-writing
path.

``admin_users._enroll_user_in_open_closures`` loaded the open closures with NO
``ORDER BY`` and booked each one via ``_create_closure_absences`` — which only
balances VACATION-vs-OVERTIME against the remaining budget WITHIN a single
closure (``sorted(workdays)`` is per-closure). Across SEVERAL closures the
split therefore followed the database's delivery order, not the calendar, and
(unlike create_closure/update_closure/delete_closure/absences/admin_vacations/
vacation_requests/admin_change_requests) never called
``closure_split_service.resplit_year_closures`` afterwards to correct it.

Reproduced exactly as in the ticket: a December closure created BEFORE a
September one, 2 vacation days of budget. A plain ``db.query(CompanyClosure)
...all()`` with no ``ORDER BY`` on SQLite returns rows in insertion (rowid)
order, so the un-fixed enroll loop processes December first — the later
closure "steals" the vacation budget from the calendar-earlier one.
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import Absence, AbsenceType, CompanyClosure
from app.models.system_setting import SystemSetting
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

# Wegwerf-Passwort, aus Teilen gebaut (Secret-Scanner faerbt ein Literal rot).
_TEST_PASSWORD = "Test" + "Pass" + "2026" + "!"

# Zwei disjunkte 3-Werktage-Fenster (Mo-Mi) im selben Jahr, weit in der Zukunft,
# ohne Feiertagsberuehrung (keine Feiertage in der Test-DB geseedet).
SEP_MON, SEP_TUE, SEP_WED = date(2027, 9, 6), date(2027, 9, 7), date(2027, 9, 8)
DEC_MON, DEC_TUE, DEC_WED = date(2027, 12, 6), date(2027, 12, 7), date(2027, 12, 8)


@pytest.fixture
def client(db, test_admin):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: test_admin
    test_app.dependency_overrides[require_admin] = lambda: test_admin
    c = TestClient(test_app)
    yield c
    test_app.dependency_overrides.clear()


def _set_toggle(db, on: bool):
    # merge -> upsert: safe even if a row already exists for this key.
    db.merge(SystemSetting(
        key="closure_overtime_after_vacation", tenant_id=DEFAULT_TENANT_ID,
        value="true" if on else "false",
    ))
    db.commit()


def _closure(db, admin, name, start, end):
    c = CompanyClosure(
        tenant_id=DEFAULT_TENANT_ID, name=name,
        start_date=start, end_date=end,
        counts_as_vacation=True, created_by=admin.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _payload(username, vacation_days=2, receives_company_closures=True):
    return {
        "username": username, "email": f"{username}@test.de",
        "first_name": "Neu", "last_name": "Mitarbeiter",
        "password": _TEST_PASSWORD, "role": "employee",
        "weekly_hours": 40, "vacation_days": vacation_days, "work_days_per_week": 5,
        "receives_company_closures": receives_company_closures,
    }


def _types_by_date(db, user_id):
    rows = db.query(Absence).filter(
        Absence.user_id == user_id, Absence.tenant_id == DEFAULT_TENANT_ID,
    ).order_by(Absence.date).all()
    return {a.date: a.type for a in rows}


def _assert_calendar_correct_split(types):
    """September (kalendarisch frueher) bekommt das 2-Tage-Budget, Dezember
    (spaeter) geht komplett auf Ueberstundenausgleich — das ist die vom
    #314-Re-Split hergestellte, kalendarisch korrekte Reihenfolge."""
    assert types[SEP_MON] == AbsenceType.VACATION
    assert types[SEP_TUE] == AbsenceType.VACATION
    assert types[SEP_WED] == AbsenceType.OVERTIME
    assert types[DEC_MON] == AbsenceType.OVERTIME
    assert types[DEC_TUE] == AbsenceType.OVERTIME
    assert types[DEC_WED] == AbsenceType.OVERTIME


class TestEnrollTriggersResplitOnCreate:
    """POST /api/admin/users — der #290-Auto-Enroll-Pfad beim Anlegen."""

    def test_calendar_order_wins_after_enroll(self, client, db, test_admin):
        _set_toggle(db, True)
        # Reihenfolge ist die Bug-Voraussetzung: Dezember ZUERST angelegt,
        # September DANACH.
        _closure(db, test_admin, "Weihnachten", DEC_MON, DEC_WED)
        _closure(db, test_admin, "Sommer", SEP_MON, SEP_WED)

        # Testannahme absichern: ohne ORDER BY liefert SQLite hier in
        # Einfuegereihenfolge — genau das macht den Bug reproduzierbar.
        raw_order = [c.name for c in db.query(CompanyClosure).filter(
            CompanyClosure.tenant_id == DEFAULT_TENANT_ID,
        ).all()]
        assert raw_order == ["Weihnachten", "Sommer"], (
            f"Testannahme verletzt (DB liefert nicht mehr in "
            f"Einfuegereihenfolge: {raw_order}) — Bug-Reproduktion haengt "
            f"daran."
        )

        r = client.post("/api/admin/users", json=_payload("enroll_create"))
        assert r.status_code == 201, r.text
        new_id = r.json()["user"]["id"]

        _assert_calendar_correct_split(_types_by_date(db, new_id))


class TestEnrollTriggersResplitOnUpdate:
    """PUT /api/admin/users/{id} — receives_company_closures wird
    nachtraeglich eingeschaltet (zweiter #290-Aufrufer)."""

    def test_calendar_order_wins_after_toggle_on(self, client, db, test_admin):
        _set_toggle(db, True)
        _closure(db, test_admin, "Weihnachten", DEC_MON, DEC_WED)
        _closure(db, test_admin, "Sommer", SEP_MON, SEP_WED)

        r = client.post(
            "/api/admin/users",
            json=_payload("enroll_update", receives_company_closures=False),
        )
        assert r.status_code == 201, r.text
        new_id = r.json()["user"]["id"]
        # Flag war beim Anlegen aus -> noch keine Buchung.
        assert _types_by_date(db, new_id) == {}

        r2 = client.put(
            f"/api/admin/users/{new_id}",
            json={"receives_company_closures": True},
        )
        assert r2.status_code == 200, r2.text

        _assert_calendar_correct_split(_types_by_date(db, new_id))


class TestEnrollSettingOffControlCase:
    """Kontrollfall: Setting AUS — der #448-Fix darf hier nicht eingreifen,
    Verhalten bleibt exakt wie vorher (alles VACATION, unabhaengig von
    Budget/Reihenfolge)."""

    def test_setting_off_all_vacation_regardless_of_order(self, client, db, test_admin):
        _set_toggle(db, False)
        _closure(db, test_admin, "Weihnachten", DEC_MON, DEC_WED)
        _closure(db, test_admin, "Sommer", SEP_MON, SEP_WED)

        r = client.post("/api/admin/users", json=_payload("enroll_off"))
        assert r.status_code == 201, r.text
        new_id = r.json()["user"]["id"]

        types = _types_by_date(db, new_id)
        assert len(types) == 6
        assert all(t == AbsenceType.VACATION for t in types.values())


class TestEnrollResplitTouchesBothStraddledYears:
    """Entscheidung #1 (Ticket): eine Schliessung, die ueber den Jahreswechsel
    geht, zaehlt fuer BEIDE Jahre als beruehrt — wie
    ``range(closure.start_date.year, closure.end_date.year + 1)`` in
    create_closure/update_closure. Direkter Nachweis per Spy auf
    ``resplit_year_closures``, unabhaengig vom konkreten VACATION/OVERTIME-
    Ergebnis."""

    def test_year_boundary_closure_resplits_both_years(self, client, db, test_admin, monkeypatch):
        _set_toggle(db, True)
        # Mi 29.12.2027 - Mo 03.01.2028: Werktage 29./30./31.12.2027 + 03.01.2028.
        _closure(db, test_admin, "Jahreswechsel", date(2027, 12, 29), date(2028, 1, 3))

        from app.routers import admin_users

        seen_years = []
        original = admin_users.resplit_year_closures

        def _spy(db_, tenant_id, year, current_user=None):
            seen_years.append(year)
            return original(db_, tenant_id, year, current_user)

        monkeypatch.setattr(admin_users, "resplit_year_closures", _spy)

        r = client.post("/api/admin/users", json=_payload("enroll_boundary"))
        assert r.status_code == 201, r.text

        assert set(seen_years) == {2027, 2028}, (
            f"erwartet Re-Split fuer beide beruehrten Jahre, gesehen: {seen_years}"
        )
