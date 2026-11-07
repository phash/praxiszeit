"""Audit 2026-11-07 (#544): Datenschutz in Fehlerlogs, Obergrenzen, Sicherungen, Mail.

S2-1 Keine Statement-Werte in ``error_logs`` (Engine ``hide_parameters``,
     Middleware und ``DBErrorHandler`` speichern nur Typ/SQLSTATE + Stapel).
S2-2 Obergrenzen an Zahlen- und Freitextfeldern → 422 statt 500.
S2-6 ``pg_dump`` mit viel stderr blockiert die Sicherung nicht.
S2-8 STARTTLS prüft das Zertifikat.
"""
import asyncio
import logging
import os
import smtplib
import ssl
import stat
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.services import error_log_service as els

SECRET_VALUES = ("Krank Rücken", "Betriebsferien: Live298", "geheim@example.de")


class _FakeDiag:
    constraint_name = "uq_absence_user_date_type"
    table_name = "absences"


class _FakePgError(Exception):
    pgcode = "23505"
    diag = _FakeDiag()

    def __str__(self):
        return ('duplicate key value violates unique constraint "uq_absence_user_date_type"\n'
                'DETAIL:  Key (user_id, date)=(65e32943-0000-0000-0000-000000000000, '
                '2027-05-25) already exists.')


def _integrity_error(hide=False):
    err = IntegrityError(
        "INSERT INTO absences (type, note) VALUES (%(type__0)s, %(note__0)s)",
        {"type__0": "SICK", "note__0": "Krank Rücken"},
        _FakePgError(),
        hide_parameters=hide,
    )
    try:
        raise err
    except IntegrityError as e:
        return e


# ── S2-1 ─────────────────────────────────────────────────────────────


def test_engine_hides_parameters():
    from app.database import engine
    assert engine.hide_parameters is True


def test_exception_summary_has_no_values():
    exc = _integrity_error()
    assert "Krank Rücken" in str(exc)  # Kontrolle: der Rohtext trägt die Werte
    summary = els.exception_summary(exc)
    assert summary == ("IntegrityError (_FakePgError: SQLSTATE 23505, "
                       "constraint uq_absence_user_date_type, table absences)")
    frames = els.exception_frames(exc)
    for text in (summary, frames):
        assert "Krank Rücken" not in text
        assert "2027-05-25" not in text
        assert "SICK" not in text


def test_exception_summary_plain_exception_is_type_only():
    assert els.exception_summary(ValueError("Name Erika Muster")) == "ValueError"


def test_capture_middleware_stores_no_statement_values(monkeypatch):
    import app.main as main
    import app.database as database
    captured = {}
    monkeypatch.setattr(main, "SessionLocal", lambda: MagicMock())
    monkeypatch.setattr(database, "set_superadmin_context", lambda db: None)
    monkeypatch.setattr(els, "log_error", lambda **kw: captured.update(kw))
    request = SimpleNamespace(
        url=SimpleNamespace(path="/api/absences/"), method="POST",
        state=SimpleNamespace(), headers={},
    )

    async def _call_next(_req):
        raise _integrity_error()

    with pytest.raises(IntegrityError):
        asyncio.run(main.capture_errors_middleware(request, _call_next))
    assert captured["level"] == "critical"
    stored = captured["message"] + (captured["traceback_str"] or "")
    for value in ("Krank Rücken", "SICK", "2027-05-25", "[parameters"):
        assert value not in stored
    assert "SQLSTATE 23505" in captured["message"]


def test_db_error_handler_stores_no_exception_text(monkeypatch):
    captured = {}
    monkeypatch.setattr(els, "log_error", lambda **kw: captured.update(kw))
    monkeypatch.setattr(els, "set_superadmin_context", lambda db: None)
    handler = els.DBErrorHandler(lambda: MagicMock())
    handler.setFormatter(logging.Formatter('%(message)s'))
    exc = _integrity_error()
    record = logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 1,
                               "Exception in ASGI application", None,
                               (type(exc), exc, exc.__traceback__))
    handler.emit(record)
    assert captured["message"] == "Exception in ASGI application"
    assert "Krank Rücken" not in (captured["traceback_str"] or "")
    assert "2027-05-25" not in (captured["traceback_str"] or "")


# ── S2-1 Fix-Runde: Container-Log, PG-Bestandscluster ────────────────


def _capture_logger(name):
    import io
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger = logging.getLogger(name)
    logger.addHandler(handler)
    logger.propagate = False
    return logger, handler, stream


def test_reraised_db_error_reaches_container_log_without_values():
    logger, handler, stream = _capture_logger("uvicorn.error.s21probe")
    try:
        assert els.install_db_error_redaction(("uvicorn.error.s21probe",)) == 1
        assert els.install_db_error_redaction(("uvicorn.error.s21probe",)) == 0  # idempotent
        exc = _integrity_error()
        logger.error("Exception in ASGI application", exc_info=(type(exc), exc, exc.__traceback__))
        logger.error("Fehler beim Speichern: %s", exc)
        out = stream.getvalue()
        for value in ("Krank Rücken", "2027-05-25", "SICK", "DETAIL", "[parameters"):
            assert value not in out, out
        assert "SQLSTATE 23505" in out
        assert "Traceback (most recent call last)" in out
        assert "test_audit_1107_s2.py" in out  # Stapel bleibt für die Fehlersuche
    finally:
        logger.removeHandler(handler)
        logger.propagate = True


def test_non_db_exceptions_stay_unchanged():
    logger, handler, stream = _capture_logger("uvicorn.error.s21plain")
    try:
        els.install_db_error_redaction(("uvicorn.error.s21plain",))
        try:
            raise ValueError("ungueltiger Monat 13")
        except ValueError:
            logger.exception("Probe")
        assert "ungueltiger Monat 13" in stream.getvalue()
    finally:
        logger.removeHandler(handler)
        logger.propagate = True


def test_main_installs_redaction_on_uvicorn_handlers():
    import importlib.util
    import app.main as main
    src = importlib.util.find_spec("app.main").origin
    text = open(src, encoding="utf-8").read()
    assert "install_db_error_redaction()" in text
    assert hasattr(main, "install_db_error_redaction")


def test_pg_log_privacy_is_noop_on_sqlite():
    from sqlalchemy import create_engine
    from app.core.pg_log_privacy import apply_log_privacy_settings
    eng = create_engine("sqlite://")
    with eng.begin() as c:
        assert apply_log_privacy_settings(c) is False


def test_env_py_applies_log_privacy_after_migrations():
    """Bestandscluster (nativ): jeder Migrationslauf setzt die Werte per
    ALTER DATABASE (Beleg gegen PG: ``test_pg_log_privacy_pg.py``)."""
    from pathlib import Path
    env_py = (Path(__file__).resolve().parents[1] / "alembic" / "env.py").read_text(encoding="utf-8")
    online = env_py[env_py.index("def run_migrations_online"):]
    assert online.index("context.run_migrations()") < online.index(
        "apply_log_privacy_settings(connection)")


# ── S2-2 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("schema,payload", [
    ("change_request.ChangeRequestCreate",
     {"request_type": "create", "proposed_break_minutes": 99999999999, "reason": "x"}),
    ("change_request.ChangeRequestCreate",
     {"request_type": "create", "entry_kind": "absence", "proposed_absence_hours": 1000,
      "reason": "x"}),
    ("change_request.ChangeRequestCreate",
     {"request_type": "create", "entry_kind": "absence", "proposed_absence_hours": -8,
      "reason": "x"}),
    ("change_request.ChangeRequestCreate", {"request_type": "create", "reason": "x" * 2001}),
    ("absence_reason.AbsenceReasonCreate",
     {"name": "Reha", "base_behavior": "paid_free", "sort_order": 99999999999}),
    ("absence_reason.AbsenceReasonUpdate", {"sort_order": -1}),
    ("time_entry.ClockOutRequest", {"break_minutes": 99999999999}),
    ("absence.AbsenceCreate", {"date": "2026-06-10", "type": "sick", "hours": 8,
                               "note": "x" * 2001}),
])
def test_schema_bounds(schema, payload):
    import importlib
    from pydantic import ValidationError
    mod_name, cls_name = schema.split(".")
    cls = getattr(importlib.import_module(f"app.schemas.{mod_name}"), cls_name)
    with pytest.raises(ValidationError):
        cls(**payload)


def test_change_request_overflow_is_422_not_500(_db_session, employee_client):
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "create", "proposed_date": "2026-11-03", "proposed_start_time": "08:00",
        "proposed_end_time": "09:00", "proposed_break_minutes": 99999999999, "reason": "probe"})
    assert r.status_code == 422, r.text
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "create", "entry_kind": "absence", "proposed_absence_type": "training",
        "proposed_absence_hours": 1000, "proposed_date": "2026-11-03", "reason": "probe"})
    assert r.status_code == 422, r.text


def test_delete_cr_absence_type_longer_than_column_is_422(_db_session, employee_client):
    """Fix-Runde: Spalte ``proposed_absence_type`` ist String(20); der
    Lösch-Antrag speichert den Wert ungeprüft → auf PG 22001 → 500."""
    import uuid
    r = employee_client.post("/api/change-requests/", json={
        "request_type": "delete", "entry_kind": "absence", "absence_id": str(uuid.uuid4()),
        "proposed_absence_type": "x" * 21, "reason": "probe"})
    assert r.status_code == 422, r.text
    from app.models.change_request import ChangeRequest
    from app.schemas.change_request import ChangeRequestCreate
    col = ChangeRequest.__table__.c.proposed_absence_type.type.length
    field = ChangeRequestCreate.model_fields["proposed_absence_type"]
    assert [m.max_length for m in field.metadata if hasattr(m, "max_length")] == [col]


def test_list_offset_bounds_are_422(_db_session, employee_client):
    # Negativer oder riesiger OFFSET war auf PostgreSQL ein DB-Fehler (500).
    for skip in (-1, 10 ** 12):
        assert employee_client.get(f"/api/absences/?skip={skip}").status_code == 422
        assert employee_client.get(f"/api/time-entries/?skip={skip}").status_code == 422
    assert employee_client.get("/api/absences/?skip=0").status_code == 200


# ── S2-6 ─────────────────────────────────────────────────────────────


def test_pg_dump_with_large_stderr_does_not_deadlock(db, default_tenant, tmp_path, monkeypatch):
    from app.services import backup_service as bs
    monkeypatch.delenv("PRAXISZEIT_BACKUP_DIR", raising=False)
    bs.update_config(db, location=str(tmp_path / "bk"))
    _scheme = "postgresql://"
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", _scheme + "su:pw@db:5432/praxiszeit")
    # Ein „pg_dump", das ZUERST 256 KB nach stderr schreibt und dann den Dump.
    fake = tmp_path / "pg_dump"
    fake.write_text("#!/bin/sh\nhead -c 262144 /dev/zero | tr '\\0' 'w' >&2\n"
                    "echo 'SELECT 1;'\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(bs, "_pg_dump_bin", lambda: str(fake))
    result = {}

    def _run():
        try:
            result["ok"] = bs.create_backup(db)
        except Exception as e:  # pragma: no cover — Fehler sichtbar machen
            result["err"] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=30)
    assert not t.is_alive(), "create_backup hängt (stderr-Deadlock)"
    assert "err" not in result, result.get("err")
    assert result["ok"].size_bytes > 0


def test_pg_dump_failure_message_comes_from_stderr(db, default_tenant, tmp_path, monkeypatch):
    from app.services import backup_service as bs
    monkeypatch.delenv("PRAXISZEIT_BACKUP_DIR", raising=False)
    bs.update_config(db, location=str(tmp_path / "bk"))
    _scheme = "postgresql://"
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", _scheme + "su:pw@db:5432/praxiszeit")
    fake = tmp_path / "pg_dump"
    fake.write_text("#!/bin/sh\necho 'pg_dump: error: connection failed' >&2\nexit 1\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(bs, "_pg_dump_bin", lambda: str(fake))
    with pytest.raises(bs.BackupError, match="connection failed"):
        bs.create_backup(db)
    assert not any(p.suffix == ".gz" for p in (tmp_path / "bk").iterdir())


# ── S2-8 ─────────────────────────────────────────────────────────────


def test_starttls_uses_verifying_context(monkeypatch):
    from app.services import mail_service
    seen = {}

    class _FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo(self):
            pass

        def starttls(self, context=None):
            seen["context"] = context

        def login(self, *a):
            pass

        def send_message(self, msg):
            pass

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    svc = mail_service.MailService(host="smtp.example", port=587, user="", password="",
                                   from_addr="noreply@example.invalid", starttls=True)
    assert svc.send(to="a@example.invalid", subject="Betreff", body_text="Text") is True
    ctx = seen["context"]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True


# Fixtures aus test_endpoints (Client mit überschriebener Anmeldung).
from tests.test_endpoints import (  # noqa: E402,F401
    _db_session, employee_client, employee_user, tenant,
)
