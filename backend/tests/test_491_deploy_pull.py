"""#491 DEP-4: ``deploy.sh`` muss die Basis-Images beim Bauen neu ziehen.

Ohne ``--pull`` nimmt ``docker compose build`` das lokal vorhandene Basis-Image
(``python:3.12-slim``, ``node:20-alpine``, ``nginx:alpine``) — Debian/Alpine-
Sicherheitsupdates, die unter demselben Tag erscheinen, kamen so nie an.

Ein nicht erreichbares Registry darf ein Deployment aber nicht verhindern (das
Pendant ``pull db`` bricht ebenfalls nicht ab): scheitert der Bau mit
``--pull``, folgt ein Bau mit den lokalen Images samt Warnung. Erst wenn auch
der scheitert, rollt das Skript zurueck — wie bisher.

Die Tests fahren das ECHTE Skript gegen Attrappen fuer ``git`` und ``docker``.
Sie brauchen das Repo-Wurzelverzeichnis (``../deploy.sh``) und ueberspringen
sich im reinen Backend-Container, wie ``test_native_pg_lifecycle.py``.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

_DEPLOY = Path(__file__).resolve().parents[2] / "deploy.sh"

pytestmark = pytest.mark.skipif(
    not _DEPLOY.is_file() or shutil.which("bash") is None,
    reason=f"deploy.sh nicht erreichbar unter {_DEPLOY} (Backend-Container ohne Repo)",
)

_GIT_STUB = """#!/usr/bin/env bash
state="$STUB_DIR/head"
[ -f "$state" ] || echo aaa > "$state"
echo "git $*" >> "$STUB_DIR/calls.log"
case "$1" in
  diff|status) exit 0 ;;
  rev-parse) cat "$state" ;;
  pull) echo bbb > "$state" ;;
  reset) echo "$3" > "$state" ;;
esac
exit 0
"""

_DOCKER_STUB = """#!/usr/bin/env bash
echo "docker $*" >> "$STUB_DIR/calls.log"
args=" $* "
if [[ "$args" == *" build "* ]]; then
  if [[ "$args" == *" --pull "* ]]; then
    [ "${FAIL_PULL_BUILD:-0}" = 1 ] && exit 1
  else
    [ "${FAIL_PLAIN_BUILD:-0}" = 1 ] && exit 1
  fi
fi
exit 0
"""


def _executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _run(tmp_path: Path, **env_overrides) -> tuple[subprocess.CompletedProcess, list[str]]:
    work = tmp_path / "repo"
    (work / "scripts").mkdir(parents=True)
    shutil.copy2(_DEPLOY, work / "deploy.sh")
    (work / ".env").write_text("ENVIRONMENT=production\n", encoding="utf-8")
    _executable(work / "scripts" / "backup-db.sh", "#!/usr/bin/env bash\nexit 0\n")

    stubs = tmp_path / "stubs"
    stubs.mkdir()
    _executable(stubs / "git", _GIT_STUB)
    _executable(stubs / "docker", _DOCKER_STUB)
    # Health-Check-Schleife nicht wirklich warten lassen.
    _executable(stubs / "sleep", "#!/usr/bin/env bash\nexit 0\n")

    env = {
        **os.environ,
        "PATH": f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}",
        "STUB_DIR": str(stubs),
        "HEALTH_TIMEOUT": "4",
        **env_overrides,
    }
    proc = subprocess.run(
        ["bash", str(work / "deploy.sh")],
        cwd=work, env=env, capture_output=True, text=True, timeout=60,
    )
    log = (stubs / "calls.log").read_text(encoding="utf-8").splitlines()
    return proc, log


def _builds(log: list[str]) -> list[str]:
    return [line for line in log if line.startswith("docker ") and " build " in f"{line} "]


def test_build_pulls_fresh_base_images(tmp_path):
    proc, log = _run(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    builds = _builds(log)
    assert builds, log
    assert " --pull " in f"{builds[0]} ", (
        f"Erster Bau ohne --pull: {builds[0]!r} — Sicherheitsupdates der "
        "Basis-Images kaemen nie an."
    )
    assert builds[0].endswith("build --pull frontend backend"), builds[0]
    assert len(builds) == 1, builds  # kein unnoetiger zweiter Bau


def test_unreachable_registry_falls_back_to_local_images(tmp_path):
    proc, log = _run(tmp_path, FAIL_PULL_BUILD="1")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    builds = _builds(log)
    assert len(builds) == 2, builds
    assert " --pull " in f"{builds[0]} "
    assert " --pull " not in f"{builds[1]} "
    assert "WARN" in proc.stdout and "--pull" in proc.stdout, proc.stdout
    assert not any(line.startswith("git reset") for line in log), log


def test_real_build_failure_still_rolls_back(tmp_path):
    proc, log = _run(tmp_path, FAIL_PULL_BUILD="1", FAIL_PLAIN_BUILD="1")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "git reset --hard aaa" in log, log
    assert not any(" up -d" in line for line in log), log
