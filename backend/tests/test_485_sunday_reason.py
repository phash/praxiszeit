"""#485: Der §10-Ausnahmegrund kommt auch auf den Admin- und Antragswegen an.

Seit #479 lassen sich im Monatsjournal Einträge an Sonn- und Feiertagen anlegen
— von Admins direkt, von Mitarbeitenden per Änderungsantrag. Auf keinem dieser
Wege kam ein Ausnahmegrund nach §10 ArbZG am Zeiteintrag an: der Admin-Router
übergab das Feld nicht an ``TimeEntry(...)``, und der Änderungsantrag kannte gar
kein Feld dafür. Die Exporte zeigen den Grund nur, wo er gespeichert ist.
"""
from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import ChangeRequest, ChangeRequestStatus, ChangeRequestType, TimeEntry
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

SUNDAY = date(2026, 3, 1)
REASON = "KV-Notdienst"


def _client(db, user, admin):
    def _override_db():
        yield db
    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = lambda: user
    test_app.dependency_overrides[require_admin] = lambda: admin
    return TestClient(test_app)


@pytest.fixture
def admin_client(db, test_admin):
    yield _client(db, test_admin, test_admin)
    test_app.dependency_overrides.clear()


@pytest.fixture
def employee_client(db, test_user, test_admin):
    yield _client(db, test_user, test_admin)
    test_app.dependency_overrides.clear()


def _entry(db, user_id):
    db.expire_all()
    return db.query(TimeEntry).filter(TimeEntry.user_id == user_id).one()


class TestAdminWeg:
    def test_anlegen_speichert_den_grund(self, admin_client, db, test_user):
        r = admin_client.post(f"/api/admin/users/{test_user.id}/time-entries", json={
            "date": SUNDAY.isoformat(), "start_time": "09:00", "end_time": "13:00",
            "break_minutes": 0, "sunday_exception_reason": REASON,
        })
        assert r.status_code == 201, r.text
        assert _entry(db, test_user.id).sunday_exception_reason == REASON

    def test_bearbeiten_speichert_den_grund(self, admin_client, db, test_user):
        e = TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=SUNDAY,
                      start_time=time(9, 0), end_time=time(13, 0), break_minutes=0)
        db.add(e)
        db.commit()
        r = admin_client.put(f"/api/admin/time-entries/{e.id}", json={
            "sunday_exception_reason": REASON,
        })
        assert r.status_code == 200, r.text
        assert _entry(db, test_user.id).sunday_exception_reason == REASON

    def test_bearbeiten_ohne_feld_laesst_den_grund_stehen(self, admin_client, db, test_user):
        e = TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=SUNDAY,
                      start_time=time(9, 0), end_time=time(13, 0), break_minutes=0,
                      sunday_exception_reason=REASON)
        db.add(e)
        db.commit()
        r = admin_client.put(f"/api/admin/time-entries/{e.id}", json={"note": "nur Notiz"})
        assert r.status_code == 200, r.text
        assert _entry(db, test_user.id).sunday_exception_reason == REASON


class TestAntragsweg:
    def test_antrag_traegt_den_grund(self, employee_client, db, test_user):
        r = employee_client.post("/api/change-requests/", json={
            "request_type": "create", "proposed_date": SUNDAY.isoformat(),
            "proposed_start_time": "09:00", "proposed_end_time": "13:00",
            "proposed_break_minutes": 0, "reason": "Dienst vergessen",
            "proposed_sunday_exception_reason": REASON,
        })
        assert r.status_code in (200, 201), r.text
        assert r.json()["proposed_sunday_exception_reason"] == REASON
        cr = db.query(ChangeRequest).filter(ChangeRequest.user_id == test_user.id).one()
        assert cr.proposed_sunday_exception_reason == REASON

    def test_genehmigung_anlegen_uebertraegt_den_grund(self, admin_client, db, test_user):
        cr = ChangeRequest(
            tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id,
            request_type=ChangeRequestType.CREATE, entry_kind="time_entry",
            status=ChangeRequestStatus.PENDING, proposed_date=SUNDAY,
            proposed_start_time=time(9, 0), proposed_end_time=time(13, 0),
            proposed_break_minutes=0, reason="Dienst vergessen",
            proposed_sunday_exception_reason=REASON,
        )
        db.add(cr)
        db.commit()
        r = admin_client.post(f"/api/admin/change-requests/{cr.id}/review",
                              json={"action": "approve"})
        assert r.status_code == 200, r.text
        assert _entry(db, test_user.id).sunday_exception_reason == REASON

    def test_genehmigung_aendern_uebertraegt_den_grund(self, admin_client, db, test_user):
        e = TimeEntry(user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=SUNDAY,
                      start_time=time(9, 0), end_time=time(12, 0), break_minutes=0)
        db.add(e)
        db.commit()
        cr = ChangeRequest(
            tenant_id=DEFAULT_TENANT_ID, user_id=test_user.id,
            request_type=ChangeRequestType.UPDATE, entry_kind="time_entry",
            status=ChangeRequestStatus.PENDING, time_entry_id=e.id,
            proposed_date=SUNDAY, proposed_start_time=time(9, 0),
            proposed_end_time=time(13, 0), proposed_break_minutes=0,
            reason="Ende korrigiert", proposed_sunday_exception_reason=REASON,
            original_date=SUNDAY, original_start_time=time(9, 0),
            original_end_time=time(12, 0), original_break_minutes=0,
        )
        db.add(cr)
        db.commit()
        r = admin_client.post(f"/api/admin/change-requests/{cr.id}/review",
                              json={"action": "approve"})
        assert r.status_code == 200, r.text
        assert _entry(db, test_user.id).sunday_exception_reason == REASON


class TestJournalLiefertDieFelder:
    """Das Monatsjournal braucht den Grund zum Vorbelegen des Bearbeiten-Formulars
    (sonst loescht ein Speichern mit leerem Feld ihn). Beim Nachsehen fiel auf,
    dass dieselbe Antwort auch die Rohstempel nie trug: ``JournalTimeEntry``
    kannte ``raw_start_time``/``raw_end_time`` nicht, die Zeile „gestempelt 07:37
    · angerechnet ab 07:45“ im Journal konnte deshalb nie erscheinen."""

    def test_journal_eintrag_traegt_grund_und_rohstempel(self, employee_client, db, test_user):
        db.add(TimeEntry(
            user_id=test_user.id, tenant_id=DEFAULT_TENANT_ID, date=SUNDAY,
            start_time=time(7, 45), end_time=time(13, 0), break_minutes=0,
            raw_start_time=time(7, 37), sunday_exception_reason=REASON,
        ))
        db.commit()
        r = employee_client.get("/api/journal/me?year=2026&month=3")
        assert r.status_code == 200, r.text
        day = next(d for d in r.json()["days"] if d["date"] == SUNDAY.isoformat())
        entry = day["time_entries"][0]
        assert entry["sunday_exception_reason"] == REASON
        assert entry["raw_start_time"] == "07:37"
        assert entry["raw_end_time"] is None
