"""Gesamtreview B3 / Spec 16.2 Nr. 8: fremde oder unbekannte Antrags-ID → 404
VOR jeder Sperre — auch an den Antragsrouten der Mitarbeitenden.

Bearbeiten und Zurückziehen eines Abwesenheitsantrags sowie das Zurückziehen
eines Änderungsantrags luden die Zeile bis dahin mit ``FOR UPDATE`` und prüften
die Eigentümerschaft erst DANACH. Ein Mitarbeiter, der die ID eines Antrags
der Kollegin schickte, sperrte damit deren Zeile (und wartete, solange die
Verwaltung sie gerade genehmigte) — die Wartezeit verriet als Timing-Orakel,
dass die ID existiert, obwohl #120 Statuscode und Text gleich hält.
Muster: ``test_write_path_locks.py::test_update_foreign_entry_takes_no_lock``.
"""
import uuid
from datetime import date, time, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models import ChangeRequest, User, UserRole
from app.models.change_request import ChangeRequestStatus, ChangeRequestType
from app.models.vacation_request import VacationRequest, VacationRequestStatus
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import (  # noqa: F401 — Fixtures
    _db_session, employee_client, employee_user, tenant,
)

_LOCKED_MODELS = (VacationRequest, ChangeRequest)


@pytest.fixture
def row_locks():
    """Jede ORM-Abfrage mit ``FOR UPDATE`` auf Antragszeilen landet im
    Protokoll (SQLite übersetzt FOR UPDATE nicht, das Statement trägt es
    trotzdem — derselbe Spion wie in ``test_write_path_locks.py``)."""
    log = []

    def on_execute(state):
        if (state.is_select
                and getattr(state.statement, "_for_update_arg", None) is not None):
            for m in state.all_mappers:
                if m.class_ in _LOCKED_MODELS:
                    log.append(m.class_.__name__)

    event.listen(Session, "do_orm_execute", on_execute)
    yield log
    event.remove(Session, "do_orm_execute", on_execute)


def _colleague(db) -> User:
    other = User(
        username="kollegin", email="kollegin@test.de",
        password_hash=auth_service.hash_password("Kollegin2025!"),
        first_name="Erika", last_name="Muster", role=UserRole.EMPLOYEE,
        weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
        is_active=True, tenant_id=DEFAULT_TENANT_ID,
    )
    db.add(other)
    db.commit()
    db.refresh(other)
    return other


def _vr(db, user) -> VacationRequest:
    vr = VacationRequest(
        user_id=user.id, tenant_id=DEFAULT_TENANT_ID,
        date=date.today() + timedelta(days=30), hours=8.0,
        absence_type="vacation", status=VacationRequestStatus.PENDING.value,
    )
    db.add(vr)
    db.commit()
    db.refresh(vr)
    return vr


def _cr(db, user) -> ChangeRequest:
    cr = ChangeRequest(
        tenant_id=DEFAULT_TENANT_ID, user_id=user.id,
        request_type=ChangeRequestType.CREATE, status=ChangeRequestStatus.PENDING,
        entry_kind="time_entry", proposed_date=date.today() - timedelta(days=1),
        proposed_start_time=time(8, 0), proposed_end_time=time(12, 0),
        proposed_break_minutes=0, reason="Gesamtreview B3",
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


# (Methode, Pfad, Nutzlast, Text der 404, Fabrik für die Zeile)
_ROUTES = [
    pytest.param("patch", "/api/vacation-requests/{id}", {"note": "fremd"},
                 "Urlaubsantrag nicht gefunden", _vr, id="vr-edit"),
    pytest.param("delete", "/api/vacation-requests/{id}", None,
                 "Urlaubsantrag nicht gefunden", _vr, id="vr-withdraw"),
    pytest.param("delete", "/api/change-requests/{id}", None,
                 "Antrag nicht gefunden", _cr, id="cr-withdraw"),
]


def _send(client, method, path, payload):
    if payload is None:
        return getattr(client, method)(path)
    return getattr(client, method)(path, json=payload)


@pytest.mark.parametrize("method, path, payload, detail, make", _ROUTES)
def test_foreign_request_takes_no_lock(_db_session, employee_user, employee_client,
                                       row_locks, method, path, payload, detail, make):
    row = make(_db_session, _colleague(_db_session))
    resp = _send(employee_client, method, path.format(id=row.id), payload)
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == detail
    assert row_locks == [], f"fremde Antragszeile gesperrt: {row_locks}"
    _db_session.expire_all()
    assert _db_session.get(type(row), row.id) is not None


@pytest.mark.parametrize("method, path, payload, detail, make", _ROUTES)
def test_unknown_request_takes_no_lock(_db_session, employee_user, employee_client,
                                       row_locks, method, path, payload, detail, make):
    resp = _send(employee_client, method, path.format(id=uuid.uuid4()), payload)
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == detail
    assert row_locks == [], row_locks


@pytest.mark.parametrize("method, path, payload, detail, make", _ROUTES)
def test_foreign_and_unknown_request_answer_identically(_db_session, employee_user,
                                                        employee_client, method, path,
                                                        payload, detail, make):
    row = make(_db_session, _colleague(_db_session))
    foreign = _send(employee_client, method, path.format(id=row.id), payload)
    unknown = _send(employee_client, method, path.format(id=uuid.uuid4()), payload)
    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()


@pytest.mark.parametrize("method, path, payload, detail, make, ok", [
    pytest.param("patch", "/api/vacation-requests/{id}", {"note": "eigen"},
                 None, _vr, 200, id="vr-edit"),
    pytest.param("delete", "/api/vacation-requests/{id}", None, None, _vr, 204, id="vr-withdraw"),
    pytest.param("delete", "/api/change-requests/{id}", None, None, _cr, 204, id="cr-withdraw"),
])
def test_own_request_is_still_locked(_db_session, employee_user, employee_client,
                                     row_locks, method, path, payload, detail, make, ok):
    """Gegenprobe: der EIGENE Antrag wird weiterhin gesperrt geladen (Audit
    2026-07-31 A3 — Zurückziehen gegen eine parallele Genehmigung). Belegt
    zugleich, dass der Spion anschlägt; sonst bestünden die Tests oben kampflos."""
    row = make(_db_session, employee_user)
    resp = _send(employee_client, method, path.format(id=row.id), payload)
    assert resp.status_code == ok, resp.text
    assert row_locks == [type(row).__name__], row_locks
