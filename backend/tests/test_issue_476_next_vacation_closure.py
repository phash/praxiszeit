"""#476: Urlaubscountdown zaehlt auch bis zur naechsten Praxisschliessung.

Seit Betriebsferien per #314-Split als Ueberstundenausgleich (OVERTIME) gebucht
werden koennen, fand ``GET /absences/next-vacation`` (nur ``type == VACATION``)
bei aufgebrauchtem Urlaubsbudget nichts mehr — der Countdown blieb leer, obwohl
die Praxis in zwei Wochen zu hat.

Grundlage sind die GEBUCHTEN Schliessungs-Abwesenheiten der Person, nicht die
Tabelle ``company_closures``: so gelten ``receives_company_closures``, das
Beschaeftigungsfenster und Fremd-Abwesenheiten von selbst.
"""
import uuid
from datetime import date

import pytest

from app.models import Absence, AbsenceType, CompanyClosure
from app.routers import absences as absences_router
from tests.conftest import DEFAULT_TENANT_ID

TODAY = date(2026, 9, 28)  # Montag


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(absences_router, "today_local", lambda: TODAY)


def _closure(db, admin, start, end, name="Herbstschließung", tenant_id=DEFAULT_TENANT_ID):
    c = CompanyClosure(
        name=name, start_date=start, end_date=end, counts_as_vacation=True,
        tenant_id=tenant_id, created_by=admin.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _absence(db, user, d, typ, closure=None, tenant_id=DEFAULT_TENANT_ID):
    a = Absence(
        user_id=user.id, tenant_id=tenant_id, date=d, type=typ, hours=8.0,
        closure_id=closure.id if closure else None,
    )
    db.add(a)
    db.commit()
    return a


def _next(db, user):
    return absences_router.get_next_vacation(db=db, current_user=user)


def test_nur_ueberstunden_schliessung_zeigt_countdown(db, test_user, test_admin):
    """Der gemeldete Fall: kein Urlaub, Schliessung komplett als OVERTIME."""
    c = _closure(db, test_admin, date(2026, 10, 12), date(2026, 10, 16))
    for day in range(12, 17):
        _absence(db, test_user, date(2026, 10, day), AbsenceType.OVERTIME, c)

    res = _next(db, test_user)
    assert res is not None
    assert res.kind == "closure"
    assert res.closure_name == "Herbstschließung"
    assert res.date == date(2026, 10, 12)
    assert res.end_date == date(2026, 10, 16)
    assert res.days_until == 14


def test_laufende_schliessung_zaehlt_ab_heute(db, test_user, test_admin):
    """Mitten in der Schliessung: 0 Tage, Beginn = heute, Ende = Schliessungsende."""
    c = _closure(db, test_admin, date(2026, 9, 21), date(2026, 10, 2))
    for day in (28, 29, 30):
        _absence(db, test_user, date(2026, 9, day), AbsenceType.OVERTIME, c)

    res = _next(db, test_user)
    assert res.kind == "closure"
    assert res.days_until == 0
    assert res.date == TODAY
    assert res.end_date == date(2026, 10, 2)


def test_frueherer_urlaub_gewinnt(db, test_user, test_admin):
    c = _closure(db, test_admin, date(2026, 10, 12), date(2026, 10, 16))
    _absence(db, test_user, date(2026, 10, 12), AbsenceType.OVERTIME, c)
    _absence(db, test_user, date(2026, 10, 5), AbsenceType.VACATION)

    res = _next(db, test_user)
    assert res.kind == "vacation"
    assert res.date == date(2026, 10, 5)
    assert res.closure_name is None


def test_fruehere_schliessung_gewinnt(db, test_user, test_admin):
    c = _closure(db, test_admin, date(2026, 10, 5), date(2026, 10, 9))
    _absence(db, test_user, date(2026, 10, 5), AbsenceType.OVERTIME, c)
    _absence(db, test_user, date(2026, 11, 2), AbsenceType.VACATION)

    res = _next(db, test_user)
    assert res.kind == "closure"
    assert res.date == date(2026, 10, 5)


def test_als_urlaub_gebuchte_schliessung_zeigt_die_schliessung(db, test_user, test_admin):
    """Ein Schliessungstag vom Typ VACATION war bisher 'Urlaub' mit nur einem
    Einzeltag (end_date=None seit #394). Jetzt: Name + ganze Spanne."""
    c = _closure(db, test_admin, date(2026, 10, 12), date(2026, 10, 16))
    _absence(db, test_user, date(2026, 10, 12), AbsenceType.VACATION, c)

    res = _next(db, test_user)
    assert res.kind == "closure"
    assert res.end_date == date(2026, 10, 16)


def test_ohne_teilnahme_kein_countdown(db, test_user, test_admin):
    """Schliessung existiert, die Person hat aber keine gebuchten Tage
    (receives_company_closures=False / ausserhalb des Fensters)."""
    _closure(db, test_admin, date(2026, 10, 12), date(2026, 10, 16))
    assert _next(db, test_user) is None


def test_vergangene_schliessung_zaehlt_nicht(db, test_user, test_admin):
    c = _closure(db, test_admin, date(2026, 9, 14), date(2026, 9, 18))
    _absence(db, test_user, date(2026, 9, 14), AbsenceType.OVERTIME, c)
    assert _next(db, test_user) is None


def test_urlaub_allein_bleibt_unveraendert(db, test_user):
    _absence(db, test_user, date(2026, 10, 5), AbsenceType.VACATION)
    res = _next(db, test_user)
    assert res.kind == "vacation"
    assert res.days_until == 7


def test_fremder_mandant_wird_ignoriert(db, test_user, test_admin):
    """F-026: eine Schliessungs-Abwesenheit mit fremder tenant_id zaehlt nicht."""
    other = uuid.uuid4()
    c = _closure(db, test_admin, date(2026, 10, 5), date(2026, 10, 9), tenant_id=other)
    _absence(db, test_user, date(2026, 10, 5), AbsenceType.OVERTIME, c, tenant_id=other)
    assert _next(db, test_user) is None
