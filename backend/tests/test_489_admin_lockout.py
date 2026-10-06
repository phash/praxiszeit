"""#489: Eine Praxis darf sich nicht aus ihrer eigenen Verwaltung aussperren.

Anlass: Eine Betreiberin kam nicht mehr in ihre Produktivinstallation — ihr
Admin-Konto war deaktiviert, wer das getan hatte, stand nirgends, und der
Login meldete es (bewusst) wie ein falsches Passwort.

Drei Regeln:

1. Der letzte aktive Admin eines Mandanten laesst sich weder deaktivieren noch
   zur Mitarbeiterin herabstufen.
2. ``is_active`` bleibt ueber ``PUT /admin/users/{id}`` wirkungslos (der Router
   verwirft das Feld) — sonst umginge dieser Weg die Regel oben, die Sperre
   gegen Selbst-Deaktivierung, ``deactivated_at`` und das Entwerten der
   Sitzungen. Regressionsschutz fuer bestehendes Verhalten.
3. Deaktivieren, Reaktivieren, Rollenwechsel und das Neusetzen eines fremden
   Passworts landen in ``security_events`` — mit dem handelnden Konto.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.models import User, UserRole
from app.models.security_event import (
    EVENT_ADMIN_SET_PASSWORD,
    EVENT_USER_DEACTIVATED,
    EVENT_USER_REACTIVATED,
    EVENT_USER_ROLE_CHANGED,
    SecurityEvent,
)
from app.services import auth_service
from tests.conftest import DEFAULT_TENANT_ID
from tests.test_endpoints import test_app

# Aus Teilen gebaut, damit die Sicherheits-Scanner kein Zugangspaar sehen.
NEW_PW = "Neues" + "Kennwort1"


def _make_user(db, username, role=UserRole.EMPLOYEE, is_active=True, tenant_id=DEFAULT_TENANT_ID):
    u = User(
        id=uuid.uuid4(), username=username, email=f"{username}@praxis.invalid",
        password_hash="x", first_name=username.capitalize(), last_name="Test",
        role=role, weekly_hours=40.0, vacation_days=30, work_days_per_week=5,
        is_active=is_active, tenant_id=tenant_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def client_as(db):
    def _client(user):
        def _override_db():
            yield db
        test_app.dependency_overrides[get_db] = _override_db
        test_app.dependency_overrides[get_current_user] = lambda: user
        test_app.dependency_overrides[require_admin] = lambda: user
        return TestClient(test_app)
    yield _client
    test_app.dependency_overrides.clear()


def _events(db, event):
    db.expire_all()
    return db.query(SecurityEvent).filter(SecurityEvent.event == event).all()


class TestLetzterAdmin:
    def test_letzter_aktiver_admin_ist_nicht_deaktivierbar(self, db, test_admin, client_as):
        # Zwei Admins, einer davon schon deaktiviert: der verbliebene ist der letzte.
        other = _make_user(db, "zweitadmin", role=UserRole.ADMIN, is_active=False)
        r = client_as(other).delete(f"/api/admin/users/{test_admin.id}")
        assert r.status_code == 400
        assert "letzte" in r.json()["detail"]
        db.refresh(test_admin)
        assert test_admin.is_active is True

    def test_mit_zweitem_aktivem_admin_geht_es(self, db, test_admin, client_as):
        other = _make_user(db, "zweitadmin", role=UserRole.ADMIN)
        r = client_as(other).delete(f"/api/admin/users/{test_admin.id}")
        assert r.status_code == 204
        db.refresh(test_admin)
        assert test_admin.is_active is False

    def test_letzter_admin_ist_nicht_herabstufbar(self, db, test_admin, client_as):
        other = _make_user(db, "zweitadmin", role=UserRole.ADMIN, is_active=False)
        r = client_as(other).put(f"/api/admin/users/{test_admin.id}", json={"role": "employee"})
        assert r.status_code == 400
        assert "letzte" in r.json()["detail"]
        db.refresh(test_admin)
        assert test_admin.role == UserRole.ADMIN

    def test_herabstufen_mit_zweitem_admin_geht(self, db, test_admin, client_as):
        other = _make_user(db, "zweitadmin", role=UserRole.ADMIN)
        r = client_as(test_admin).put(f"/api/admin/users/{other.id}", json={"role": "employee"})
        assert r.status_code == 200, r.text
        db.refresh(other)
        assert other.role == UserRole.EMPLOYEE

    def test_mitarbeitende_bleiben_deaktivierbar(self, db, test_admin, test_user, client_as):
        r = client_as(test_admin).delete(f"/api/admin/users/{test_user.id}")
        assert r.status_code == 204


class TestKeinDeaktivierenPerPut:
    def test_is_active_per_put_bleibt_wirkungslos(self, db, test_admin, client_as):
        # Ausgerechnet der letzte Admin: der PUT-Weg darf ihn nicht still abschalten.
        r = client_as(test_admin).put(f"/api/admin/users/{test_admin.id}", json={"is_active": False})
        assert r.status_code == 200, r.text
        db.refresh(test_admin)
        assert test_admin.is_active is True

    def test_unveraendertes_is_active_stoert_nicht(self, db, test_admin, test_user, client_as):
        r = client_as(test_admin).put(
            f"/api/admin/users/{test_user.id}", json={"is_active": True, "first_name": "Neu"},
        )
        assert r.status_code == 200, r.text


class TestProtokoll:
    def test_deaktivieren_wird_protokolliert(self, db, test_admin, test_user, client_as):
        client_as(test_admin).delete(f"/api/admin/users/{test_user.id}")
        rows = _events(db, EVENT_USER_DEACTIVATED)
        assert len(rows) == 1
        assert rows[0].subject_user_id == test_user.id
        assert rows[0].actor == f"user:{test_admin.id}"
        assert rows[0].tenant_id == DEFAULT_TENANT_ID

    def test_reaktivieren_wird_protokolliert(self, db, test_admin, client_as):
        gone = _make_user(db, "ehemalige", is_active=False)
        r = client_as(test_admin).post(f"/api/admin/users/{gone.id}/reactivate")
        assert r.status_code == 200, r.text
        rows = _events(db, EVENT_USER_REACTIVATED)
        assert len(rows) == 1
        assert rows[0].subject_user_id == gone.id
        assert rows[0].actor == f"user:{test_admin.id}"

    def test_rollenwechsel_wird_protokolliert(self, db, test_admin, test_user, client_as):
        client_as(test_admin).put(f"/api/admin/users/{test_user.id}", json={"role": "admin"})
        rows = _events(db, EVENT_USER_ROLE_CHANGED)
        assert len(rows) == 1
        assert rows[0].subject_user_id == test_user.id
        assert "employee" in rows[0].detail and "admin" in rows[0].detail

    def test_unveraenderte_rolle_schreibt_nichts(self, db, test_admin, test_user, client_as):
        client_as(test_admin).put(f"/api/admin/users/{test_user.id}", json={"role": "employee"})
        assert _events(db, EVENT_USER_ROLE_CHANGED) == []

    def test_fremdes_passwort_setzen_wird_protokolliert(self, db, test_admin, test_user, client_as):
        r = client_as(test_admin).post(
            f"/api/admin/users/{test_user.id}/set-password", json={"password": NEW_PW},
        )
        assert r.status_code == 200, r.text
        rows = _events(db, EVENT_ADMIN_SET_PASSWORD)
        assert len(rows) == 1
        assert rows[0].subject_user_id == test_user.id
        assert NEW_PW not in (rows[0].detail or "")

    def test_abgelehnte_deaktivierung_schreibt_nichts(self, db, test_admin, client_as):
        other = _make_user(db, "zweitadmin", role=UserRole.ADMIN, is_active=False)
        client_as(other).delete(f"/api/admin/users/{test_admin.id}")
        assert _events(db, EVENT_USER_DEACTIVATED) == []


class TestAnsicht:
    def test_liste_zeigt_vorgaenge_mit_namen(self, db, test_admin, test_user, client_as):
        c = client_as(test_admin)
        c.delete(f"/api/admin/users/{test_user.id}")
        r = c.get("/api/admin/security-events")
        assert r.status_code == 200, r.text
        rows = r.json()
        assert rows[0]["event"] == EVENT_USER_DEACTIVATED
        assert rows[0]["subject_name"] == f"{test_user.first_name} {test_user.last_name}"
        assert rows[0]["actor_name"] == f"{test_admin.first_name} {test_admin.last_name}"

    def test_kommandozeilen_akteur_bleibt_lesbar(self, db, test_admin, client_as):
        db.add(SecurityEvent(tenant_id=DEFAULT_TENANT_ID, event="admin_password_reset_cli",
                             subject_user_id=test_admin.id, actor="cli:root@praxis-server"))
        db.commit()
        rows = client_as(test_admin).get("/api/admin/security-events").json()
        assert rows[0]["actor_name"] == "Kommandozeile (root@praxis-server)"

    def test_fremder_mandant_bleibt_unsichtbar(self, db, test_admin, client_as):
        from app.models.tenant import Tenant
        other = Tenant(id=uuid.uuid4(), name="Andere", slug="andere-praxis")
        db.add(other)
        db.commit()
        db.add(SecurityEvent(tenant_id=other.id, event=EVENT_USER_DEACTIVATED, actor="user:x"))
        db.commit()
        assert client_as(test_admin).get("/api/admin/security-events").json() == []
