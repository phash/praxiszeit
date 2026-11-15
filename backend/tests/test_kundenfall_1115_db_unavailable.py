"""Kundenfall 2026-11-15, Log-Audit Punkt 10 (RT-4): faellt die Datenbank-
verbindung waehrend einer Anfrage weg (PostgreSQL startet neu, Dienst wird
gestoppt), kam ein nacktes HTTP 500 samt ``error_logs``-Zeile.

Jetzt: Verbindungsfehler (SQLSTATE 08xxx, 57P01/57P02/57P03 oder die
psycopg2-Texte ohne SQLSTATE) → 503 mit ``Retry-After`` und deutschem Text,
WARNING ueber einen eigenen Logger, kein ``error_logs``-Eintrag. Alle anderen
Datenbankfehler bleiben 500; das 22P02-Verhalten (#483) bleibt unberuehrt.
"""
import logging

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy.exc import DataError, IntegrityError, InterfaceError, OperationalError

from app.core import db_errors
from app.core.db_errors import (
    DB_UNAVAILABLE_DETAIL, is_connection_loss, register_db_error_handlers,
)


class _FakePgError(Exception):
    def __init__(self, pgcode=None, text="pg error"):
        super().__init__(text)
        self.pgcode = pgcode


def _app_raising(exc_factory):
    a = FastAPI()
    register_db_error_handlers(a)
    seen = {}

    @a.middleware("http")
    async def _probe(request: Request, call_next):
        response = await call_next(request)
        seen["db_unavailable"] = getattr(request.state, "db_unavailable", False)
        return response

    @a.get("/boom")
    def boom():
        raise exc_factory()

    return a, seen


@pytest.mark.parametrize("code", ["08006", "08001", "08P01", "57P01", "57P02", "57P03"])
def test_connection_sqlstates_become_503(code):
    app, seen = _app_raising(lambda: OperationalError("SELECT 1", {}, _FakePgError(code)))
    r = TestClient(app).get("/boom")
    assert r.status_code == 503
    assert r.json() == {"detail": DB_UNAVAILABLE_DETAIL}
    assert r.headers["retry-after"] == "5"
    # Markierung fuer capture_errors_middleware: keine error_logs-Zeile.
    assert seen["db_unavailable"] is True


@pytest.mark.parametrize("text", [
    "server closed the connection unexpectedly\n\tThis probably means the server terminated abnormally",
    'connection to server at "127.0.0.1", port 5432 failed: Connection refused',
])
def test_psycopg2_connection_texts_without_sqlstate_become_503(text):
    app, _ = _app_raising(lambda: OperationalError("SELECT 1", {}, _FakePgError(None, text)))
    r = TestClient(app).get("/boom")
    assert r.status_code == 503
    assert "Datenbank kurz nicht erreichbar" in r.json()["detail"]


def test_interface_error_connection_already_closed_becomes_503():
    app, _ = _app_raising(lambda: InterfaceError("SELECT 1", {}, _FakePgError(None, "connection already closed")))
    assert TestClient(app).get("/boom").status_code == 503


def test_invalidated_connection_flag_becomes_503():
    def _exc():
        e = OperationalError("SELECT 1", {}, _FakePgError(None, "whatever"))
        e.connection_invalidated = True
        return e
    app, _ = _app_raising(_exc)
    assert TestClient(app).get("/boom").status_code == 503


@pytest.mark.parametrize("exc_factory", [
    lambda: OperationalError("SELECT 1", {}, _FakePgError("53300", "too many connections")),
    lambda: OperationalError("SELECT 1", {}, _FakePgError("40P01", "deadlock detected")),
    lambda: IntegrityError("INSERT", {}, _FakePgError("23505", "duplicate key")),
])
def test_other_db_errors_stay_500(exc_factory):
    app, _ = _app_raising(exc_factory)
    r = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500


def test_22p02_still_422():
    app, _ = _app_raising(lambda: DataError("SELECT 1", {}, _FakePgError("22P02")))
    assert TestClient(app).get("/boom").status_code == 422


def test_connection_loss_logged_as_warning_on_own_logger(caplog):
    app, _ = _app_raising(lambda: OperationalError("SELECT 1", {}, _FakePgError("57P01", "terminating connection due to administrator command")))
    with caplog.at_level(logging.WARNING, logger=db_errors.connection_logger.name):
        TestClient(app).get("/boom")
    recs = [r for r in caplog.records if r.name == db_errors.connection_logger.name]
    assert recs and recs[0].levelno == logging.WARNING
    assert "/boom" in recs[0].getMessage()
    # Nicht am DBErrorHandler (der lauscht nur auf uvicorn.error/fastapi).
    assert not db_errors.connection_logger.name.startswith(("uvicorn", "fastapi"))


def test_is_connection_loss_ignores_non_db_errors():
    assert is_connection_loss(RuntimeError("server closed the connection unexpectedly")) is False


def test_capture_errors_middleware_skips_db_unavailable(monkeypatch):
    """Die echte App schreibt bei 503 aus Verbindungsverlust keine error_logs-Zeile."""
    import app.main as main
    calls = []
    monkeypatch.setattr(main, "_capture_error_row", lambda *a, **k: calls.append(k))

    class _Req:
        class state:  # noqa: N801
            db_unavailable = True

    class _Resp:
        status_code = 503

    async def _call_next(_r):
        return _Resp()

    import asyncio
    asyncio.run(main.capture_errors_middleware(_Req(), _call_next))
    assert calls == []


@pytest.mark.parametrize("text", [
    'connection to server at "127.0.0.1", port 5432 failed: FATAL:  password authentication failed for user "praxiszeit_app"',
    'connection to server at "127.0.0.1", port 5432 failed: FATAL:  database "praxiszeit" does not exist',
    'connection to server at "127.0.0.1", port 5432 failed: FATAL:  sorry, too many clients already',
    'connection to server at "127.0.0.1", port 5432 failed: FATAL:  no pg_hba.conf entry for host "127.0.0.1"',
])
def test_permanent_connect_errors_stay_500(text):
    """Review-Fund: Konfigurationsfehler beim Verbinden (falsches App-Passwort nach
    Reparatur/Portwechsel, fehlende DB, zu viele Verbindungen) kommen ohne SQLSTATE
    und sind KEIN kurzer Ausfall — sie bleiben 500 mit Traceback/error_logs."""
    assert is_connection_loss(OperationalError("SELECT 1", {}, _FakePgError(None, text))) is False
    app, _ = _app_raising(lambda: OperationalError("SELECT 1", {}, _FakePgError(None, text)))
    assert TestClient(app, raise_server_exceptions=False).get("/boom").status_code == 500


def test_connection_loss_warning_contains_cause_excerpt(caplog):
    text = ('connection to server at "127.0.0.1", port 5432 failed: Connection refused\n'
            '\tIs the server running on that host and accepting TCP/IP connections?')
    app, _ = _app_raising(lambda: OperationalError("SELECT 1", {}, _FakePgError(None, text)))
    with caplog.at_level(logging.WARNING, logger=db_errors.connection_logger.name):
        TestClient(app).get("/boom")
    msg = [r for r in caplog.records if r.name == db_errors.connection_logger.name][0].getMessage()
    assert "Connection refused" in msg
    # nur die erste Zeile, ohne Steuerzeichen
    assert "Is the server running" not in msg and "\n" not in msg and "\t" not in msg
