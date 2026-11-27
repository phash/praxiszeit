"""#585: Urlaubskonto für das gewählte Jahr auf der Seite „Abwesenheiten".

Kundenwunsch (Praxis Braumann): Mitarbeitende wollen für die Urlaubsplanung des
kommenden Jahres sehen, wie viele Tage noch verplant werden können — inklusive
Betriebsferien und offener Anträge.

``GET /api/dashboard/vacation?year=`` liefert dafür zusätzlich:
- ``carryover_days`` = Übertrag (Budget − Anspruch)
- ``closure_days``  = davon Betriebsferien (gebuchte VACATION-Zeilen mit ``closure_id``)
- ``pending_days``  = offene Urlaubsanträge, nur der Anteil im Jahr
- ``plannable_days`` = Rest − offene Anträge
"""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.absence import Absence, AbsenceType
from app.models.company_closure import CompanyClosure
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.models.year_carryover import YearCarryover


def _app() -> FastAPI:
    from app.routers import dashboard as dashboard_router
    from app.core.limiter import limiter

    app = FastAPI()
    limiter.enabled = False
    app.state.limiter = limiter
    app.include_router(dashboard_router.router)
    return app


_APP = _app()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    _APP.dependency_overrides.clear()


def _get(db, user, year):
    def override_db():
        yield db

    _APP.dependency_overrides[get_db] = override_db
    _APP.dependency_overrides[get_current_user] = lambda: user
    r = TestClient(_APP).get(f"/api/dashboard/vacation?year={year}")
    assert r.status_code == 200, r.text
    return r.json()


def _vacation(db, user, day, closure_id=None, half_day=False):
    db.add(Absence(
        tenant_id=user.tenant_id, user_id=user.id, date=day,
        type=AbsenceType.VACATION, hours=Decimal("4.0") if half_day else Decimal("8.0"),
        half_day=half_day, closure_id=closure_id,
    ))


def _request(db, user, start, end, status=VacationRequestStatus.PENDING.value,
             absence_type="vacation", half_day=False):
    db.add(VacationRequest(
        tenant_id=user.tenant_id, user_id=user.id, date=start, end_date=end,
        hours=Decimal("8.0"), absence_type=absence_type, half_day=half_day, status=status,
    ))


def _closure(db, admin, start, end):
    c = CompanyClosure(tenant_id=admin.tenant_id, name="Sommer", start_date=start,
                       end_date=end, created_by=admin.id)
    db.add(c)
    db.flush()
    return c


def test_ohne_planung_ist_alles_frei(db, test_user):
    data = _get(db, test_user, 2027)
    assert data["carryover_days"] == 0
    assert data["closure_days"] == 0
    assert data["pending_days"] == 0
    assert data["plannable_days"] == pytest.approx(data["remaining_days"]) == pytest.approx(30)


def test_gebucht_betriebsferien_und_offene_antraege(db, test_user, test_admin):
    closure = _closure(db, test_admin, dt.date(2027, 8, 2), dt.date(2027, 8, 3))
    _vacation(db, test_user, dt.date(2027, 8, 2), closure_id=closure.id)
    _vacation(db, test_user, dt.date(2027, 8, 3), closure_id=closure.id)
    _vacation(db, test_user, dt.date(2027, 5, 10))
    # Offener Antrag Mo 14.06.–Mi 16.06.2027 = 3 Arbeitstage
    _request(db, test_user, dt.date(2027, 6, 14), dt.date(2027, 6, 16))
    db.commit()

    data = _get(db, test_user, 2027)
    assert data["used_days"] == pytest.approx(3)
    assert data["closure_days"] == pytest.approx(2)
    assert data["pending_days"] == pytest.approx(3)
    assert data["remaining_days"] == pytest.approx(27)
    assert data["plannable_days"] == pytest.approx(24)


def test_antrag_ueber_den_jahreswechsel_zaehlt_nur_den_anteil_im_jahr(db, test_user):
    # Mo 28.12.2026 – Di 05.01.2027: 2027 = Fr 01.01., Mo 04.01., Di 05.01.
    _request(db, test_user, dt.date(2026, 12, 28), dt.date(2027, 1, 5))
    db.commit()

    assert _get(db, test_user, 2027)["pending_days"] == pytest.approx(3)


def test_halbtagsantrag_kostet_die_haelfte(db, test_user):
    _request(db, test_user, dt.date(2027, 3, 1), dt.date(2027, 3, 1), half_day=True)
    db.commit()

    assert _get(db, test_user, 2027)["pending_days"] == pytest.approx(0.5)


@pytest.mark.parametrize("status, absence_type", [
    (VacationRequestStatus.APPROVED.value, "vacation"),
    (VacationRequestStatus.REJECTED.value, "vacation"),
    (VacationRequestStatus.PENDING.value, "training"),
])
def test_nur_offene_urlaubsantraege_zaehlen(db, test_user, status, absence_type):
    _request(db, test_user, dt.date(2027, 6, 14), dt.date(2027, 6, 16),
             status=status, absence_type=absence_type)
    db.commit()

    assert _get(db, test_user, 2027)["pending_days"] == 0


def test_antraege_anderer_personen_zaehlen_nicht(db, test_user, test_admin):
    _request(db, test_admin, dt.date(2027, 6, 14), dt.date(2027, 6, 16))
    db.commit()

    assert _get(db, test_user, 2027)["pending_days"] == 0


def test_uebertrag_wird_ausgewiesen(db, test_user):
    db.add(YearCarryover(tenant_id=test_user.tenant_id, user_id=test_user.id, year=2027,
                         vacation_days=Decimal("4.5"), overtime_hours=Decimal("0")))
    db.commit()

    data = _get(db, test_user, 2027)
    assert data["carryover_days"] == pytest.approx(4.5)
    assert data["budget_days"] == pytest.approx(34.5)
    assert data["plannable_days"] == pytest.approx(34.5)


# --- offene Änderungsanträge auf Abwesenheiten -------------------------------
#
# Mitarbeitende können Urlaub auch per Änderungsantrag (entry_kind="absence")
# beantragen. Offene Anträge zählen wie bei der Budget-Prüfung der Genehmigung:
# CREATE = der Tag, UPDATE = Netto-Neuverbrauch, DELETE = 0.

from app.models.change_request import ChangeRequest, ChangeRequestStatus, ChangeRequestType
from app.models.public_holiday import PublicHoliday


def _cr(db, user, request_type, proposed_date=None, absence_type=None, absence=None,
        status=ChangeRequestStatus.PENDING):
    db.add(ChangeRequest(
        tenant_id=user.tenant_id, user_id=user.id, request_type=request_type, status=status,
        entry_kind="absence", absence_id=absence.id if absence else None,
        proposed_date=proposed_date, proposed_absence_type=absence_type, reason="Test",
    ))


def _absence(db, user, day, absence_type):
    a = Absence(tenant_id=user.tenant_id, user_id=user.id, date=day, type=absence_type,
                hours=Decimal("8.0"), half_day=False)
    db.add(a)
    db.flush()
    return a


def test_cr_create_urlaub_zaehlt_als_beantragt(db, test_user):
    _cr(db, test_user, ChangeRequestType.CREATE, dt.date(2027, 6, 14), "vacation")
    db.commit()

    data = _get(db, test_user, 2027)
    assert data["pending_days"] == pytest.approx(1)
    assert data["plannable_days"] == pytest.approx(29)


@pytest.mark.parametrize("absence_type, status", [
    ("sick", ChangeRequestStatus.PENDING),
    ("vacation", ChangeRequestStatus.APPROVED),
    ("vacation", ChangeRequestStatus.REJECTED),
])
def test_cr_create_andere_typen_oder_erledigt_zaehlen_nicht(db, test_user, absence_type, status):
    _cr(db, test_user, ChangeRequestType.CREATE, dt.date(2027, 6, 14), absence_type, status=status)
    db.commit()

    assert _get(db, test_user, 2027)["pending_days"] == 0


def test_cr_create_im_anderen_jahr_oder_am_feiertag_zaehlt_nicht(db, test_user):
    db.add(PublicHoliday(tenant_id=test_user.tenant_id, date=dt.date(2027, 5, 6),
                         name="Christi Himmelfahrt", year=2027))
    _cr(db, test_user, ChangeRequestType.CREATE, dt.date(2027, 5, 6), "vacation")
    _cr(db, test_user, ChangeRequestType.CREATE, dt.date(2028, 6, 14), "vacation")
    db.commit()

    assert _get(db, test_user, 2027)["pending_days"] == 0


def test_cr_update_krank_zu_urlaub_zaehlt(db, test_user):
    sick = _absence(db, test_user, dt.date(2027, 3, 1), AbsenceType.SICK)
    _cr(db, test_user, ChangeRequestType.UPDATE, absence_type="vacation", absence=sick)
    db.commit()

    assert _get(db, test_user, 2027)["pending_days"] == pytest.approx(1)


def test_cr_update_urlaub_verschieben_im_jahr_kostet_nichts(db, test_user):
    vac = _absence(db, test_user, dt.date(2027, 3, 1), AbsenceType.VACATION)
    _cr(db, test_user, ChangeRequestType.UPDATE, proposed_date=dt.date(2027, 3, 2),
        absence_type="vacation", absence=vac)
    db.commit()

    data = _get(db, test_user, 2027)
    assert data["pending_days"] == 0
    assert data["plannable_days"] == pytest.approx(29)


def test_cr_update_urlaub_ins_folgejahr_zaehlt_dort(db, test_user):
    vac = _absence(db, test_user, dt.date(2027, 12, 20), AbsenceType.VACATION)
    _cr(db, test_user, ChangeRequestType.UPDATE, proposed_date=dt.date(2028, 1, 10),
        absence_type="vacation", absence=vac)
    db.commit()

    assert _get(db, test_user, 2027)["pending_days"] == 0  # Freigabe erst mit Genehmigung
    assert _get(db, test_user, 2028)["pending_days"] == pytest.approx(1)


def test_cr_delete_gibt_erst_mit_genehmigung_frei(db, test_user):
    vac = _absence(db, test_user, dt.date(2027, 3, 1), AbsenceType.VACATION)
    _cr(db, test_user, ChangeRequestType.DELETE, absence=vac)
    db.commit()

    data = _get(db, test_user, 2027)
    assert data["pending_days"] == 0
    assert data["plannable_days"] == pytest.approx(29)


def test_cr_anderer_personen_zaehlen_nicht(db, test_user, test_admin):
    _cr(db, test_admin, ChangeRequestType.CREATE, dt.date(2027, 6, 14), "vacation")
    db.commit()

    assert _get(db, test_user, 2027)["pending_days"] == 0
