"""Docker: uvicorn ohne Superuser-Verbindung (Audit 2026-11-07 S3-13, Fix-Runde).

Der Backend-Container fuehrt seine Migrationen mit ``DATABASE_URL_MIGRATIONS``
aus. Bis zur Fix-Runde blieb diese Superuser-URL fuer die ganze Laufzeit in der
Umgebung von uvicorn (Datensicherung der Weboberflaeche). Jetzt richtet
``docker-start.sh`` nach den Migrationen die nur lesende Rolle
``praxiszeit_backup`` ein und startet uvicorn ohne die Superuser-URL.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.core import backup_role

_BACKEND = Path(__file__).resolve().parents[1]


def test_role_is_read_only_and_bypasses_rls_only():
    sql = "\n".join(backup_role.role_sql("ab" * 32, "praxiszeit"))
    assert "NOSUPERUSER" in sql and "NOCREATEROLE" in sql and "NOCREATEDB" in sql
    assert "BYPASSRLS" in sql and "NOREPLICATION" in sql
    assert "GRANT pg_read_all_data TO praxiszeit_backup" in sql
    assert 'GRANT CONNECT ON DATABASE "praxiszeit" TO praxiszeit_backup' in sql
    assert "pg_write" not in sql and "pg_execute_server_program" not in sql


@pytest.mark.parametrize("db", ['x"; DROP', "a b", ""])
def test_database_name_is_validated(db):
    with pytest.raises(ValueError):
        backup_role.role_sql("ab" * 32, db)


def test_password_must_be_hex():
    with pytest.raises(ValueError):
        backup_role.role_sql("x'; ALTER ROLE", "praxiszeit")


def test_url_for_the_backup_role(monkeypatch):
    executed = []

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def exec_driver_sql(self, statement):
            executed.append(statement)

    class _Engine:
        def connect(self):
            return _Conn()

        def dispose(self):
            pass

    import sqlalchemy
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda url, **kw: _Engine())
    scheme = "postgresql+psycopg2" + "://"
    url = backup_role.ensure_backup_role(scheme + "su" + ":geheim@db:5432/praxiszeit")
    assert url.startswith("postgresql" + "://praxiszeit_backup:")
    assert url.endswith("@db:5432/praxiszeit")
    password = url.split("praxiszeit_backup:", 1)[1].split("@", 1)[0]
    assert len(password) == 64 and "geheim" not in url
    assert any(password in s for s in executed)


def test_main_without_migrations_url_fails_softly(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL_MIGRATIONS", raising=False)
    assert backup_role.main() == 1
    out = capsys.readouterr()
    assert out.out == "" and "WARNUNG" in out.err


def test_main_never_prints_the_url_on_failure(monkeypatch, capsys):
    scheme = "postgresql" + "://"
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", scheme + "su" + ":geheim@nirgends.invalid:1/praxiszeit")

    def _boom(url):
        raise RuntimeError("could not connect to " + url)

    monkeypatch.setattr(backup_role, "ensure_backup_role", _boom)
    assert backup_role.main() == 1
    out = capsys.readouterr()
    assert out.out == "" and "geheim" not in out.err


def test_dockerfile_starts_through_the_start_script():
    dockerfile = (_BACKEND / "Dockerfile").read_text(encoding="utf-8")
    assert 'CMD ["sh", "/app/docker-start.sh"]' in dockerfile
    script = (_BACKEND / "docker-start.sh").read_text(encoding="utf-8")
    assert "\r" not in script
    lines = [ln.strip() for ln in script.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert lines.index("alembic upgrade head") < next(
        i for i, ln in enumerate(lines) if "app.core.backup_role" in ln)
    exec_line = next(ln for ln in lines if ln.startswith("exec "))
    assert exec_line.startswith("exec env -u DATABASE_URL_MIGRATIONS uvicorn app.main:app")


def test_start_script_drops_the_superuser_url(tmp_path):
    """Die echte Datei mit Attrappen fuer alembic/python/uvicorn."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "alembic").write_text("#!/bin/sh\necho alembic:$DATABASE_URL_MIGRATIONS >> \"$LOG\"\n")
    (bin_dir / "python").write_text("#!/bin/sh\necho backup-url\n")
    (bin_dir / "uvicorn").write_text(
        "#!/bin/sh\necho \"uvicorn:${DATABASE_URL_MIGRATIONS-UNSET}:${DATABASE_URL_BACKUP-UNSET}\" >> \"$LOG\"\n")
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    log = tmp_path / "log"
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "LOG": str(log), "DATABASE_URL_MIGRATIONS": "su-url"}
    subprocess.run(["sh", str(_BACKEND / "docker-start.sh")], env=env, check=True)
    assert log.read_text().splitlines() == ["alembic:su-url", "uvicorn:UNSET:backup-url"]
    # Rolle nicht einrichtbar -> uvicorn startet trotzdem, ohne Backup-URL
    (bin_dir / "python").write_text("#!/bin/sh\nexit 1\n")
    log.unlink()
    subprocess.run(["sh", str(_BACKEND / "docker-start.sh")], env=env, check=True)
    assert log.read_text().splitlines() == ["alembic:su-url", "uvicorn:UNSET:UNSET"]
