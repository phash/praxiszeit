"""#483: Eine ungueltige ID darf keinen HTTP 500 ausloesen.

PostgreSQL lehnt einen Nicht-UUID-String in einer UUID-Spalte mit SQLSTATE
``22P02`` (``invalid_text_representation``) ab; SQLAlchemy reicht das als
``DataError`` durch, und ohne Handler wird daraus ein 500 samt Eintrag in
``error_logs``. Rund ein Dutzend Endpunkte nahmen IDs als freien ``str`` an.

SQLite akzeptiert den String klaglos — hier wird deshalb der Handler selbst
gegen ein nachgebautes ``DataError`` geprueft. Dass PostgreSQL tatsaechlich
genau diesen Code liefert, belegt ``test_invalid_uuid_postgres.py``.
"""
import asyncio
import logging
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import DataError

from app.core.db_errors import invalid_text_representation_handler, register_db_error_handlers
from app.database import get_db
from app.middleware.auth import get_current_user, require_admin
from app.routers import absences


class _FakePgError(Exception):
    """Steht fuer psycopg2.errors.* — relevant sind ``pgcode`` und der Text."""

    def __init__(self, pgcode, detail=None):
        super().__init__(detail or f"pg error {pgcode}")
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


def test_invalid_text_representation_is_logged_as_warning(caplog):
    """#491 API-1: der Handler darf einen 22P02 nicht spurlos schlucken.

    Ein ungueltiger Wert kann auch aus dem Programm selbst stammen (etwa ein
    falscher Enum-Wert) — dann ist er ein Fehler im Server, keiner in der
    Eingabe. Die 422 bleibt, aber der Vorgang muss im Anwendungsprotokoll
    auffindbar sein: Methode, Route und die Meldung der Datenbank.
    """
    client = TestClient(_app_raising("22P02"))
    with caplog.at_level(logging.WARNING, logger="app.core.db_errors"):
        r = client.get("/boom")
    assert r.status_code == 422
    records = [rec for rec in caplog.records if rec.name == "app.core.db_errors"]
    assert len(records) == 1, caplog.records
    rec = records[0]
    assert rec.levelno == logging.WARNING
    msg = rec.getMessage()
    assert "22P02" in msg
    assert "GET /boom" in msg
    assert "pg error 22P02" in msg  # die Meldung der Datenbank selbst


def test_logged_warning_uses_the_route_template_and_only_the_first_line(caplog):
    """Route-Vorlage statt Rohpfad (ein Bot mit wechselnden IDs erzeugt dann
    gleichlautende Zeilen) und nur die erste Zeile der Datenbankmeldung: die
    Folgezeilen (``LINE 1: …``) zitieren SQL samt eingesetzter Werte — genau
    das, was F-007 aus den Protokollen heraushaelt."""
    a = FastAPI()
    register_db_error_handlers(a)

    @a.get("/items/{item_id}")
    def item(item_id: str):
        raise DataError("SELECT 1", {}, _FakePgError("22P02", detail=(
            'invalid input syntax for type uuid: "kaputt"\n'
            "LINE 1: ... WHERE users.email = 'jemand@example.org' AND users.id = 'kaputt'"
        )))

    with caplog.at_level(logging.WARNING, logger="app.core.db_errors"):
        r = TestClient(a).get("/items/kaputt")
    assert r.status_code == 422
    msg = next(rec.getMessage() for rec in caplog.records if rec.name == "app.core.db_errors")
    assert "/items/{item_id}" in msg
    assert 'invalid input syntax for type uuid: "kaputt"' in msg
    assert "LINE 1" not in msg
    assert "jemand@example.org" not in msg


def test_handler_tolerates_a_missing_request(caplog):
    """``test_invalid_uuid_postgres.py`` ruft den Handler ohne Request auf —
    das Protokollieren darf daran nicht scheitern."""
    exc = DataError("SELECT 1", {}, _FakePgError("22P02"))
    with caplog.at_level(logging.WARNING, logger="app.core.db_errors"):
        response = asyncio.run(invalid_text_representation_handler(None, exc))
    assert response.status_code == 422
    assert any(rec.name == "app.core.db_errors" for rec in caplog.records)


def test_other_data_errors_are_not_logged_by_the_handler(caplog):
    # 22001 laeuft weiter als 500 in capture_errors_middleware/error_logs —
    # der Handler selbst schreibt dafuer keine zweite Zeile.
    client = TestClient(_app_raising("22001"), raise_server_exceptions=False)
    with caplog.at_level(logging.WARNING, logger="app.core.db_errors"):
        assert client.get("/boom").status_code == 500
    assert not [rec for rec in caplog.records if rec.name == "app.core.db_errors"]


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
