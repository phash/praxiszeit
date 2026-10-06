"""#483: Eine ungueltige ID darf keinen HTTP 500 ausloesen.

PostgreSQL lehnt einen Nicht-UUID-String in einer UUID-Spalte mit SQLSTATE
``22P02`` (``invalid_text_representation``) ab; SQLAlchemy reicht das als
``DataError`` durch, und ohne Handler wird daraus ein 500 samt Eintrag in
``error_logs``. Rund ein Dutzend Endpunkte nahmen IDs als freien ``str`` an.

SQLite akzeptiert den String klaglos — hier wird deshalb der Handler selbst
gegen ein nachgebautes ``DataError`` geprueft. Dass PostgreSQL tatsaechlich
genau diesen Code liefert, belegt ``test_invalid_uuid_postgres.py``.
"""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import DataError

from app.core.db_errors import register_db_error_handlers
from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.routers import absences


class _FakePgError(Exception):
    """Steht fuer psycopg2.errors.* — relevant ist nur ``pgcode``."""

    def __init__(self, pgcode):
        super().__init__(f"pg error {pgcode}")
        self.pgcode = pgcode


def _app_raising(pgcode):
    a = FastAPI()
    register_db_error_handlers(a)

    @a.get("/boom")
    def boom():
        raise DataError("SELECT 1", {}, _FakePgError(pgcode))

    return a


def test_invalid_text_representation_becomes_422():
    client = TestClient(_app_raising("22P02"))
    r = client.get("/boom")
    assert r.status_code == 422
    assert "Ungültige ID" in r.json()["detail"]


def test_other_data_errors_stay_server_errors():
    # 22001 = String zu lang: ein Fehler im Server, keine falsche Eingabe.
    client = TestClient(_app_raising("22001"), raise_server_exceptions=False)
    assert client.get("/boom").status_code == 500


def test_main_app_registers_the_handler():
    from app.main import app as main_app
    from app.core.db_errors import invalid_text_representation_handler

    assert main_app.exception_handlers.get(DataError) is invalid_text_representation_handler


@pytest.fixture
def admin_client(db, test_admin):
    a = FastAPI()
    a.include_router(absences.router)

    def od():
        yield db

    a.dependency_overrides[get_db] = od
    a.dependency_overrides[get_current_user] = lambda: test_admin
    a.dependency_overrides[require_admin] = lambda: test_admin
    return TestClient(a)


def test_create_absence_rejects_malformed_user_id(admin_client):
    r = admin_client.post("/api/absences/", json={
        "date": date(2026, 3, 2).isoformat(),
        "type": "sick",
        "hours": 8,
        "user_id": "xyz",
    })
    assert r.status_code == 422
