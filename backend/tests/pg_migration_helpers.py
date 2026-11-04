"""Gemeinsame Bausteine der Postgres-Migrationstests (073/074/075): Alembic als
Unterprozess (kein ``python -m alembic``, cwd-Shadowing), md5-Schnappschuss und
eine Wegwerf-Datenbank auf dem Server."""
import os
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]


def alembic(url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL_MIGRATIONS": url}
    proc = subprocess.run(
        [sys.executable, "-c", f"from alembic.config import main; main({list(args)!r})"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=900,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout + proc.stderr


def md5(conn, sql: str) -> tuple:
    return tuple(conn.execute(text(
        f"SELECT count(*), md5(string_agg(t::text, ',' ORDER BY t::text)) FROM ({sql}) t"
    )).one())


@contextmanager
def scratch_database(admin_url: str, prefix: str):
    name = f"{prefix}_{uuid.uuid4().hex[:10]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
