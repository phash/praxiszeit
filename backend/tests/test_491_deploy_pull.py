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
last="${@: -1}"
if [[ "$args" == *" build "* ]]; then
  if [[ "$args" == *" --pull "* ]]; then
    [ "${FAIL_PULL_BUILD:-0}" = 1 ] && exit 1
  else
    [ "${FAIL_PLAIN_BUILD:-0}" = 1 ] && exit 1
  fi
fi
# Laufende Container: `compose ... ps -q <dienst>` -> Container-ID.
if [[ "$args" == *" ps -q "* ]]; then
  [ "${NO_RUNNING:-0}" = 1 ] && exit 0
  echo "cid-$last"
  exit 0
fi
# `inspect -f '{{.Image}} {{.Config.Image}}' cid-<dienst>` -> "<id> <name>".
if [ "$1" = inspect ]; then
  echo "sha256:old-${last#cid-} praxiszeit-${last#cid-}"
  exit 0
fi
if [ "$1" = tag ]; then
  [ "${FAIL_TAG:-0}" = 1 ] && exit 1
  # Nur das Zuruecktaggen im Rollback scheitern lassen.
  [ "${FAIL_RETAG:-0}" = 1 ] && [[ "$2" == *:pre-deploy ]] && exit 1
fi
# Health-Check im Backend-Container.
if [[ "$args" == *" exec "* ]]; then
  [ "${FAIL_HEALTH:-0}" = 1 ] && exit 1
fi
# Das erste `up -d` des Deploys (nicht das des Rollbacks).
if [[ "$args" == *" up -d"* && "$args" != *" --no-build "* ]]; then
  if [ "${FAIL_UP:-0}" = 1 ] && [ ! -f "$STUB_DIR/up-failed" ]; then
    touch "$STUB_DIR/up-failed"
    exit 1
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
    # Ein teilweise geglueckter Bau kann einen Namen schon umgehaengt haben:
    # die Namen zeigen danach wieder auf die laufenden Images.
    rollback = log[log.index("git reset --hard aaa") + 1:]
    assert "docker tag praxiszeit-backend:pre-deploy praxiszeit-backend" in rollback, rollback
    assert "docker tag praxiszeit-frontend:pre-deploy praxiszeit-frontend" in rollback, rollback


# --- Rollback nach `build --pull` (#491 DEP-4, Review-Nachzug) ----------------
#
# Nach `build --pull` zeigen die lokalen Basis-Tags (python:3.12-slim, ...) auf
# die FRISCHEN Images. Ein Rollback per Neubau entstuende auf genau diesen —
# kommt der Fehler vom neuen Basis-Image, stellte er nichts wieder her (und ein
# Bau-Fehler mitten im Rollback brach unter `set -e` ab). Deshalb gibt das
# Skript den laufenden App-Images VOR dem Bau eine zweite Referenz
# `<name>:pre-deploy` und taggt im Rollback von dort zurueck; neu gebaut wird
# nur, wenn keine Referenz entstand. Die blosse Image-ID genuegt nicht: im
# containerd-Image-Store (Docker 29) ist das alte Image weg, sobald `build`
# den Namen umhaengt — auch wenn ein Container es noch nutzt.

def _after(log: list[str], marker: str) -> list[str]:
    return log[log.index(marker) + 1:]


_KEEP_BACKEND = "docker tag sha256:old-backend praxiszeit-backend:pre-deploy"
_KEEP_FRONTEND = "docker tag sha256:old-frontend praxiszeit-frontend:pre-deploy"
_BACK_BACKEND = "docker tag praxiszeit-backend:pre-deploy praxiszeit-backend"
_BACK_FRONTEND = "docker tag praxiszeit-frontend:pre-deploy praxiszeit-frontend"


def test_running_images_get_a_second_reference_before_the_build(tmp_path):
    proc, log = _run(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    first_build = next(i for i, line in enumerate(log) if line in _builds(log))
    assert _KEEP_BACKEND in log[:first_build], log
    assert _KEEP_FRONTEND in log[:first_build], log
    # Erfolg: kein Zuruecktaggen, die Zusatz-Referenzen fallen am Ende weg.
    assert _BACK_BACKEND not in log and _BACK_FRONTEND not in log, log
    tail = log[first_build:]
    assert "docker rmi praxiszeit-backend:pre-deploy" in tail, tail
    assert "docker rmi praxiszeit-frontend:pre-deploy" in tail, tail


def test_health_failure_restores_the_previous_images_without_rebuild(tmp_path):
    proc, log = _run(tmp_path, FAIL_HEALTH="1")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "git reset --hard aaa" in log, log
    rollback = _after(log, "git reset --hard aaa")
    assert _BACK_BACKEND in rollback, rollback
    assert _BACK_FRONTEND in rollback, rollback
    assert any(line.endswith("up -d --no-build") for line in rollback), rollback
    assert not _builds(rollback), (
        f"Rollback baut neu {_builds(rollback)} — auf den frisch gezogenen Basis-Images."
    )


def test_health_failure_without_recorded_images_falls_back_to_rebuild(tmp_path):
    proc, log = _run(tmp_path, FAIL_HEALTH="1", NO_RUNNING="1")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    rollback = _after(log, "git reset --hard aaa")
    assert not any(line.startswith("docker tag ") for line in rollback), rollback
    assert _builds(rollback), rollback
    assert any(line.endswith("up -d") for line in rollback), rollback


def test_health_failure_without_a_kept_reference_falls_back_to_rebuild(tmp_path):
    proc, log = _run(tmp_path, FAIL_HEALTH="1", FAIL_TAG="1")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    rollback = _after(log, "git reset --hard aaa")
    assert _builds(rollback), rollback
    assert any(line.endswith("up -d") for line in rollback), rollback


def test_up_failure_restores_the_previous_images_without_rebuild(tmp_path):
    proc, log = _run(tmp_path, FAIL_UP="1")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    rollback = _after(log, "git reset --hard aaa")
    assert _BACK_BACKEND in rollback, rollback
    assert _BACK_FRONTEND in rollback, rollback
    assert any(line.endswith("up -d --no-build") for line in rollback), rollback
    assert not _builds(rollback), rollback


def test_health_failure_with_failing_retag_falls_back_to_rebuild(tmp_path):
    proc, log = _run(tmp_path, FAIL_HEALTH="1", FAIL_RETAG="1")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    rollback = _after(log, "git reset --hard aaa")
    assert _builds(rollback), rollback
    assert any(line.endswith("up -d") for line in rollback), rollback


# --- Kunden-Bundle (#491 DEP-4, Review-Nachzug) -------------------------------

_BUILD_RELEASE = _DEPLOY.parent / "tools" / "build-release.sh"


def _docker_readme() -> str:
    src = _BUILD_RELEASE.read_text(encoding="utf-8")
    start = src.index('cat > "${DOCKER_STAGE}/DOCKER-README.md" << DOCKEREOF')
    return src[start:src.index("\nDOCKEREOF\n", start)]


def test_docker_bundle_readme_update_pulls_fresh_base_images():
    """Die Updateanleitung IM pzweb-Docker-Bundle (groesste Docker-Nutzergruppe)
    muss die Basis-Images neu ziehen — sonst baut `up -d --build` weiter auf
    den lokal gecachten python:3.12-slim/node:20-alpine/nginx:alpine, und die
    Debian/Alpine-Sicherheitsupdates aus DEP-4 kommen dort nie an."""
    readme = _docker_readme()
    section = readme[readme.index("## Datensicherung / Update"):]
    section = section[:section.index("\n## ", 1)]
    lines = [line.strip() for line in section.splitlines()]
    pull_db = next(i for i, line in enumerate(lines) if line.startswith("docker compose pull db"))
    build = next(i for i, line in enumerate(lines) if line.startswith("docker compose build --pull"))
    restore = next(i for i, line in enumerate(lines) if line.startswith("bash restore.sh"))
    assert pull_db < build < restore, section
    # Der Startschritt steht konkret da (wie UPDATE.md 2a), nicht als Platzhalter.
    assert "Stack starten" not in section, section
    start = next(i for i, line in enumerate(lines)
                 if line.startswith("docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d"))
    assert build < start < restore, section
    assert "--build" not in lines[start], lines[start]
