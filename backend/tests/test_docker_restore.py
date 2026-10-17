"""Docker-Restore (Gesamtreview 1.20): ``restore.sh`` muss das Backend wirklich
neu starten und in eine LEERE Datenbank einspielen.

Migrationen laufen bei Docker nur im CMD des Backend-Containers
(``alembic upgrade head && uvicorn``). Bis 1.20 endete jeder Restore-Weg mit
``docker compose up -d backend`` — bei laufendem Backend mit unveraenderter
Konfiguration ein No-op („Container … Running“). Der eingespielte Dump setzt
``alembic_version`` auf den Stand der Vorversion zurueck, das neue Backend
arbeitete danach gegen das alte Schema: nach dem Update auf 1.20 scheiterte
jede Abfrage auf ``users`` an der fehlenden Spalte ``work_blocks`` (Login
HTTP 500 fuer alle), waehrend ``/api/health`` weiter „healthy“ meldete.
Nachgestellt mit echtem PostgreSQL 18 und dem Backend-Image: 072-Dump in den
README-Ablauf → ``alembic_version`` 072, Login 500.

Zweiter Befund derselben Nachstellung: ``--clean --if-exists`` entfernt nur,
was im Dump vorkommt. Eine Tabelle, die erst eine neuere Version angelegt hat
(z. B. ``security_events`` aus 071 mit Fremdschluessel auf ``users``), bleibt
stehen — der Restore eines aelteren Backups bricht dann mit „cannot drop
constraint users_pkey … security_events_subject_user_id_fkey depends on it“
ab (Sprung 1.18 → 1.20, ``update-pg-major.sh`` von 1.9.x). Deshalb legt
``restore.sh`` die Datenbank vor dem Einspielen frisch an, wie
``restore-backup.bat`` unter Windows.

Die Tests fahren die ECHTEN Skripte gegen eine Attrappe fuer ``docker`` (wie
``test_491_deploy_pull.py``). Sie brauchen das Repo-Wurzelverzeichnis und
ueberspringen sich im reinen Backend-Container.
"""
from __future__ import annotations

import gzip
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_TOOLS = _REPO / "tools" / "docker"
_RESTORE = _TOOLS / "restore.sh"

pytestmark = pytest.mark.skipif(
    not _RESTORE.is_file() or shutil.which("bash") is None,
    reason=f"restore.sh nicht erreichbar unter {_RESTORE} (Backend-Container ohne Repo)",
)

_DOCKER_STUB = r"""#!/usr/bin/env bash
echo "docker $*" >> "$STUB_DIR/calls.log"
args=" $* "
if [[ "$args" == *" exec -T db psql "* ]]; then
  # Ohne -c/-f liest psql den Dump von stdin = das eigentliche Einspielen.
  if [[ "$args" != *" -c "* && "$args" != *" -f "* ]]; then
    cat > "$STUB_DIR/restored.sql"
    exit "${FAIL_RESTORE:-0}"
  fi
  exit 0
fi
if [[ "$args" == *" exec -T db pg_dump "* ]]; then
  printf -- '-- dump\n--\n-- PostgreSQL database dump complete\n--\n'
  exit 0
fi
if [[ "$args" == *" exec -T db test "* ]]; then exit 0; fi
# `docker ps -a --filter volume=…` (update-pg-major): kein Container haelt das Volume.
if [[ "$1" == "ps" ]]; then exit 0; fi
if [[ "$args" == *" ps "* ]]; then
  if [[ "$args" == *" -q "* ]]; then
    if [[ "$args" == *" backend "* ]]; then
      [ "${NO_BACKEND:-0}" = 1 ] || echo "cid-backend"
    else
      echo "cid-db"
    fi
    exit 0
  fi
  if [[ "$args" == *" backend "* ]]; then
    echo "${BACKEND_STATE:-running} ${BACKEND_HEALTH:-healthy}"
  elif [[ "$args" == *"{{.Health}}"* ]]; then
    echo healthy
  else
    echo running
  fi
  exit 0
fi
if [[ "$1" == "inspect" ]]; then
  if [[ "$args" == *"StartedAt"* ]]; then echo "2026-10-17T10:00:00.123456789Z"; else echo "praxiszeit_postgres_data"; fi
  exit 0
fi
if [[ "$args" == *" logs "* ]]; then
  printf 'INFO  [alembic] Running upgrade\n\n*** HINWEIS (Migration 073) ***\n0 Konten\n*** ENDE HINWEIS ***\nINFO: Uvicorn running\n'
  exit 0
fi
exit 0
"""

_COMPLETE_DUMP = "-- dump\nSELECT 1;\n--\n-- PostgreSQL database dump complete\n--\n\n\\unrestrict abc\n"


def _bundle(tmp_path: Path) -> Path:
    """Docker-Bundle-Layout: Skripte NEBEN docker-compose.yml + .env."""
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    for name in ("restore.sh", "backup.sh", "update-pg-major.sh"):
        shutil.copy(_TOOLS / name, bundle / name)
    (bundle / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (bundle / ".env").write_text(
        "POSTGRES_USER=praxiszeit\nPOSTGRES_DB=praxiszeit\n", encoding="utf-8"
    )
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    docker = stubs / "docker"
    docker.write_text(_DOCKER_STUB, encoding="utf-8")
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    return bundle


def _env(tmp_path: Path, **extra: str) -> dict:
    return {
        **os.environ,
        "PATH": f"{tmp_path / 'stubs'}:{os.environ['PATH']}",
        "STUB_DIR": str(tmp_path),
        "RESTORE_WAIT_SECONDS": "6",
        **extra,
    }


def _dump(tmp_path: Path, text: str = _COMPLETE_DUMP) -> Path:
    path = tmp_path / "praxiszeit_20261017_120000.sql.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _run_restore(tmp_path: Path, dump: Path | None = None, **extra: str):
    bundle = _bundle(tmp_path)
    dump = dump or _dump(tmp_path)
    proc = subprocess.run(
        ["bash", str(bundle / "restore.sh"), str(dump)],
        env=_env(tmp_path, **extra), capture_output=True, text=True, timeout=60,
        stdin=subprocess.DEVNULL,
    )
    return proc, _calls(tmp_path)


def _idx(calls: list[str], needle: str) -> int:
    hits = [i for i, line in enumerate(calls) if needle in line]
    assert hits, f"{needle!r} fehlt in {calls}"
    return hits[0]


def _restore_idx(calls: list[str]) -> int:
    hits = [i for i, line in enumerate(calls)
            if " exec -T db psql " in line and " -c " not in line and " -f " not in line]
    assert len(hits) == 1, calls
    return hits[0]


def test_restore_restarts_the_running_backend_so_migrations_run(tmp_path):
    proc, calls = _run_restore(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    stop = _idx(calls, "compose stop backend")
    restore = _restore_idx(calls)
    start = _idx(calls, "compose start backend")
    assert stop < restore < start, calls
    # Das No-op von frueher darf nicht mehr der „Neustart“ sein.
    assert not any("up -d backend" in line for line in calls), calls
    assert (tmp_path / "restored.sql").read_text(encoding="utf-8") == _COMPLETE_DUMP


def test_restore_loads_the_dump_into_a_fresh_database(tmp_path):
    proc, calls = _run_restore(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    drop = _idx(calls, 'DROP DATABASE IF EXISTS "praxiszeit" WITH (FORCE)')
    assert " -d postgres " in calls[drop], calls[drop]
    assert 'CREATE DATABASE "praxiszeit"' in calls[drop], calls[drop]
    stop = _idx(calls, "compose stop backend")
    restore = _restore_idx(calls)
    assert stop < drop < restore, calls
    # Rechte wie bei der Erstinitialisierung (GRANT CONNECT liegt nicht im Dump).
    grants = _idx(calls, "-f /docker-entrypoint-initdb.d/01_init-db-user.sql")
    assert restore < grants, calls


def test_restore_waits_until_the_backend_is_healthy(tmp_path):
    proc, calls = _run_restore(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    start = _idx(calls, "compose start backend")
    assert any(i > start and " ps " in line and " backend" in line
               for i, line in enumerate(calls)), calls


def test_restore_shows_the_migration_notes_of_this_start(tmp_path):
    """Die Hinweise der Migrationen (073: uebernommene Konten, Besonderheiten)
    stehen im Container-Log — nur die dieses Starts, nicht die der frischen
    Datenbank davor."""
    proc, calls = _run_restore(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # Startzeit vom Daemon (StartedAt), nicht von der Host-Uhr.
    logs = _idx(calls, "compose logs --no-log-prefix --since 2026-10-17T10:00:00.123456789Z backend")
    assert _idx(calls, "compose start backend") < logs, calls
    assert "*** HINWEIS (Migration 073) ***\n0 Konten\n*** ENDE HINWEIS ***" in proc.stdout, proc.stdout
    assert "Uvicorn" not in proc.stdout, proc.stdout
    assert "docker compose logs --since " in proc.stdout, proc.stdout


def test_restore_reports_a_backend_that_does_not_come_back(tmp_path):
    proc, calls = _run_restore(tmp_path, BACKEND_STATE="restarting", BACKEND_HEALTH="")
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "docker compose logs backend" in proc.stderr, proc.stderr


def test_restore_reports_a_backend_that_never_turns_healthy(tmp_path):
    proc, calls = _run_restore(tmp_path, BACKEND_HEALTH="starting", RESTORE_WAIT_SECONDS="1")
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "docker compose logs backend" in proc.stderr, proc.stderr


def test_restore_keeps_a_stopped_backend_stopped(tmp_path):
    proc, calls = _run_restore(tmp_path, NO_BACKEND="1")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not any("start backend" in line or "stop backend" in line for line in calls), calls
    _restore_idx(calls)
    assert "docker compose up -d" in proc.stdout, proc.stdout


def test_restore_refuses_an_incomplete_dump_before_touching_anything(tmp_path):
    truncated = _dump(tmp_path, "-- dump\nCREATE TABLE x ();\n")
    proc, calls = _run_restore(tmp_path, dump=truncated)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert not any("stop backend" in line or "DROP DATABASE" in line or " psql " in line
                   for line in calls), calls


def test_failed_restore_keeps_the_backend_stopped(tmp_path):
    """Halb eingespielte Datenbank: ein Neustart liesse alembic darauf los und
    der Bootstrap legte einen frischen Admin an — das Backend bleibt aus."""
    proc, calls = _run_restore(tmp_path, FAIL_RESTORE="3")
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert not any("start backend" in line for line in calls), calls
    assert "restore.sh" in proc.stderr, proc.stderr


def test_update_pg_major_ends_with_a_migrated_backend(tmp_path):
    """``update-pg-major.sh`` meldete „Fertig“ nach einem No-op-``up -d backend``."""
    bundle = _bundle(tmp_path)
    proc = subprocess.run(
        ["bash", str(bundle / "update-pg-major.sh")],
        env=_env(tmp_path), capture_output=True, text=True, timeout=60,
        stdin=subprocess.DEVNULL, cwd=bundle,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    calls = _calls(tmp_path)
    up = _idx(calls, "compose up -d --build")
    restore = _restore_idx(calls)
    start = _idx(calls, "compose start backend")
    assert up < restore < start, calls
    assert not any("up -d backend" in line for line in calls[restore:]), calls
    assert "Fertig" in proc.stdout, proc.stdout


# --- Anleitungen: kein `up -d backend` als „Neustart“ nach einem Restore --------

_BUILD_RELEASE = _REPO / "tools" / "build-release.sh"


def _docker_readme() -> str:
    src = _BUILD_RELEASE.read_text(encoding="utf-8")
    start = src.index('cat > "${DOCKER_STAGE}/DOCKER-README.md" << DOCKEREOF')
    return src[start:src.index("\nDOCKEREOF\n", start)]


def _restore_followups(text: str) -> list[str]:
    """Die erste Befehlszeile nach jedem Restore-Befehl."""
    lines = [line.strip() for line in text.splitlines()]
    out = []
    for i, line in enumerate(lines):
        if line.startswith("bash restore.sh") or line.startswith("bash tools/docker/restore.sh") \
                or ("| docker compose exec -T db psql" in line and not line.startswith(">")):
            following = [nxt for nxt in lines[i + 1:] if nxt and not nxt.startswith("#")]
            out.append(following[0] if following else "")
    return out


# Gesamtreview 1.20 (Nachzug): README.md und setup-anleitung.md §9.4 fuehrten
# weiter den alten Weg (`gunzip | docker compose exec -T db psql` bei laufendem
# Backend, ohne ON_ERROR_STOP, README sogar „idempotent … kein manuelles
# Leeren“). Sie fehlten in dieser Liste — und eine Anleitung ganz OHNE Neustart
# bestand die Pruefung auf ein nachfolgendes `up -d backend` ohnehin.
_GUIDES = [
    "DOCKER-README", "docs/UPDATE.md", "docs/INSTALLATION.md", "docs/BACKUP.md",
    "README.md", "docs/setup-anleitung.md",
]


def _guide(name: str) -> str:
    return _docker_readme() if name == "DOCKER-README" else (_REPO / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", _GUIDES)
def test_no_guide_restarts_the_backend_with_a_no_op(name):
    followups = _restore_followups(_guide(name))
    assert followups, f"kein Restore-Befehl in {name} gefunden"
    for nxt in followups:
        assert not nxt.startswith("docker compose up -d backend"), (name, nxt)


def _chunks(text: str) -> list[tuple[bool, list[str]]]:
    """Absaetze und Codebloecke: (ist_codeblock, zeilen). Ein Codeblock endet am
    schliessenden Zaun, ein Absatz an der naechsten Leerzeile."""
    out, cur, fenced = [], [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            if fenced:
                out.append((True, cur))
                cur, fenced = [], False
            else:
                if cur:
                    out.append((False, cur))
                cur, fenced = [], True
            continue
        if not fenced and not line.strip():
            if cur:
                out.append((False, cur))
            cur = []
            continue
        cur.append(line)
    if cur:
        out.append((fenced, cur))
    return out


@pytest.mark.parametrize("name", _GUIDES)
def test_manual_restore_is_wrapped_in_backend_stop_and_start(name):
    """Wer von Hand durch ``psql`` einspielt, haelt das Backend vorher an und
    startet es danach wieder — sonst arbeitet es gegen den Stand des Backups,
    und erst sein naechster Start migrierte."""
    for fenced, lines in _chunks(_guide(name)):
        manual = [i for i, line in enumerate(lines)
                  if "| docker compose exec -T db psql" in line and not line.lstrip().startswith(">")]
        if not manual:
            continue
        block = "\n".join(lines)
        assert "docker compose stop backend" in block, (name, block)
        assert "docker compose start backend" in block, (name, block)
        assert "ON_ERROR_STOP=1" in block, (name, block)
        if fenced:
            stop = next(i for i, l in enumerate(lines) if "docker compose stop backend" in l)
            start = max(i for i, l in enumerate(lines) if "docker compose start backend" in l)
            assert stop < manual[0] and manual[-1] < start, (name, block)


def test_docker_readme_points_to_the_migration_output():
    readme = _docker_readme()
    section = readme[readme.index("## Datensicherung / Update"):]
    section = section[:section.index("\n## ", 1)]
    assert "docker compose logs backend" in section, section
    assert "*** HINWEIS (Migration 073) ***" in section, section
    assert "UPDATE.md" in section, section
