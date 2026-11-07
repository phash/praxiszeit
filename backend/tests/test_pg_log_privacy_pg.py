"""Audit 2026-11-07 (S2-1) Fix-Runde: PostgreSQL-Log ohne Statement-Werte
auch auf nativen BESTANDS-Clustern — gegen echtes PostgreSQL.

``pg_init`` schreibt ``log_min_error_statement``/``log_error_verbosity`` nur in
die postgresql.conf NEUER Cluster. ``alembic/env.py`` setzt sie deshalb bei
jedem Migrationslauf per ``ALTER DATABASE … SET``. Dieser Test liest die Werte
in einer neuen Sitzung mit ``SHOW`` zurueck (als Migrationsrolle und, falls
``APP_DB_URL`` gesetzt ist, als ``praxiszeit_app``).

Ohne PostgreSQL-URL wird das Modul uebersprungen; laeuft in
``scripts/local-ci.sh`` Schritt 2 und im PostgreSQL-Schritt der GH-CI.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

ADMIN_DB_URL = os.environ.get("ADMIN_DB_URL") or os.environ.get("DATABASE_URL_MIGRATIONS")
if not ADMIN_DB_URL or not ADMIN_DB_URL.startswith("postgres"):
    pytest.skip("test_pg_log_privacy_pg.py braucht DATABASE_URL_MIGRATIONS (PostgreSQL).",
                allow_module_level=True)

from app.core.pg_log_privacy import LOG_PRIVACY_SETTINGS, apply_log_privacy_settings


def _show(url: str) -> dict[str, str]:
    eng = create_engine(url)
    try:
        with eng.connect() as c:
            return {k: c.execute(text(f"SHOW {k}")).scalar() for k in LOG_PRIVACY_SETTINGS}
    finally:
        eng.dispose()


def _db_settings(eng) -> set[str]:
    """Datenbank-Ebene (``ALTER DATABASE … SET``) — unabhaengig davon, ob der
    Server selbst schon mit ``-c log_min_error_statement=panic`` laeuft (Docker)."""
    with eng.connect() as c:
        row = c.execute(text(
            "SELECT setconfig FROM pg_db_role_setting WHERE setrole = 0 AND setdatabase = "
            "(SELECT oid FROM pg_database WHERE datname = current_database())"
        )).scalar()
    return set(row or [])


def _reset(eng) -> None:
    with eng.begin() as c:
        db = c.dialect.identifier_preparer.quote(c.execute(text("SELECT current_database()")).scalar())
        for k in LOG_PRIVACY_SETTINGS:
            c.execute(text(f"ALTER DATABASE {db} RESET {k}"))


@pytest.fixture
def admin_engine():
    eng = create_engine(ADMIN_DB_URL)
    with eng.connect() as c:
        if not c.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar():
            eng.dispose()
            pytest.skip("Migrationsrolle ist kein Superuser")
    _reset(eng)
    yield eng
    with eng.begin() as c:  # Endzustand wie nach einem echten Migrationslauf
        apply_log_privacy_settings(c)
    eng.dispose()


def test_settings_apply_to_new_sessions(admin_engine):
    # Ausgangslage Bestandscluster: nichts auf Datenbank-Ebene gesetzt.
    assert not any(e.startswith("log_") for e in _db_settings(admin_engine))
    with admin_engine.begin() as c:
        assert apply_log_privacy_settings(c) is True
    assert {"log_min_error_statement=panic", "log_error_verbosity=terse"} <= _db_settings(admin_engine)
    assert _show(ADMIN_DB_URL) == LOG_PRIVACY_SETTINGS
    app_url = os.environ.get("APP_DB_URL")
    if app_url:
        assert _show(app_url) == LOG_PRIVACY_SETTINGS


def test_idempotent(admin_engine):
    for _ in range(2):
        with admin_engine.begin() as c:
            assert apply_log_privacy_settings(c) is True
    assert _show(ADMIN_DB_URL) == LOG_PRIVACY_SETTINGS


def test_non_superuser_is_a_noop_and_keeps_the_transaction_usable(admin_engine):
    role = f"pz_nosu_{uuid.uuid4().hex[:8]}"
    with admin_engine.begin() as c:
        c.execute(text(f"CREATE ROLE {role} NOLOGIN NOSUPERUSER"))
    try:
        with admin_engine.begin() as c:
            c.execute(text(f"SET LOCAL ROLE {role}"))
            assert apply_log_privacy_settings(c) is False
            assert c.execute(text("SELECT 1")).scalar() == 1
        assert not any(e.startswith("log_") for e in _db_settings(admin_engine))
    finally:
        with admin_engine.begin() as c:
            c.execute(text(f"DROP ROLE {role}"))

