"""Nur lesende Datenbank-Rolle für die Datensicherung (Docker, Audit 2026-11-07
S3-13, Fix-Runde).

Der Backend-Container führt seine Migrationen selbst aus und braucht dafür die
Superuser-Verbindung ``DATABASE_URL_MIGRATIONS``. uvicorn braucht sie nicht:
``docker-start.sh`` ruft dieses Modul nach ``alembic upgrade head`` auf und
startet uvicorn danach OHNE ``DATABASE_URL_MIGRATIONS``. Die Datensicherung der
Weboberfläche bekommt stattdessen ``DATABASE_URL_BACKUP`` — wie nativ die Rolle
``praxiszeit_backup`` (``pg_read_all_data`` + ``BYPASSRLS``, kein Superuser,
kein Schreibrecht, kein ``COPY … TO PROGRAM``). Das Passwort wird bei jedem
Start neu gewürfelt und lebt nur in der Umgebung von uvicorn.

    python -m app.core.backup_role    # druckt DATABASE_URL_BACKUP, Exit 1 bei Fehler
"""
from __future__ import annotations

import os
import re
import secrets
import sys

ROLE = "praxiszeit_backup"
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def role_sql(password: str, database: str) -> list[str]:
    """Die Anweisungen (idempotent). ``password`` ist Hex, ``database`` ein
    geprüfter Bezeichner — beides ohne Anführungsprobleme."""
    if not re.fullmatch(r"[0-9a-f]{32,}", password):
        raise ValueError("Passwort muss Hex sein")
    if not _IDENT_RE.match(database):
        raise ValueError(f"Ungültiger Datenbankname: {database!r}")
    return [
        "DO $$ BEGIN\n"
        f"  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ROLE}') THEN\n"
        f"    CREATE ROLE {ROLE} LOGIN;\n"
        "  END IF;\n"
        "END $$",
        f"ALTER ROLE {ROLE} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
        f"NOREPLICATION BYPASSRLS PASSWORD '{password}'",
        f"GRANT pg_read_all_data TO {ROLE}",
        f'GRANT CONNECT ON DATABASE "{database}" TO {ROLE}',
    ]


def ensure_backup_role(migrations_url: str) -> str:
    """Rolle anlegen/angleichen und die Verbindungs-URL dafür liefern."""
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from sqlalchemy.pool import NullPool

    url = make_url(migrations_url)
    database = url.database or "praxiszeit"
    password = secrets.token_hex(32)
    engine = create_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for statement in role_sql(password, database):
                conn.exec_driver_sql(statement)
    finally:
        engine.dispose()
    return url.set(drivername="postgresql", username=ROLE, password=password).render_as_string(
        hide_password=False
    )


def main() -> int:
    migrations_url = os.environ.get("DATABASE_URL_MIGRATIONS", "").strip()
    if not migrations_url:
        print("WARNUNG: DATABASE_URL_MIGRATIONS fehlt - keine Backup-Rolle.", file=sys.stderr)
        return 1
    try:
        print(ensure_backup_role(migrations_url))
    except Exception as exc:  # noqa: BLE001 - Start darf daran nicht scheitern
        print(
            f"WARNUNG: Backup-Rolle {ROLE} nicht eingerichtet ({type(exc).__name__}) - "
            "Sicherungen aus der Weboberfläche sind bis zum nächsten Start nicht möglich.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - Kommandozeile
    sys.exit(main())
