"""Gesamtreview B8: ``backend/.dockerignore`` haelt Host-Reste aus dem Image.

Ohne die Datei kopierte ``COPY . .`` im Backend-Dockerfile alles aus
``backend/`` ins Image: eine Host-``test.db`` (entsteht bei jedem pytest-Lauf
mit gemountetem ``backend/``, auch als ``-wal``/``-shm``/``-journal``),
``__pycache__``/``.pyc``, ``.pytest_cache`` und lokalen Werkzeugzustand
(``.claude``). Die Testsuite im Container (``local-ci`` Schritt 1) oeffnet
``sqlite:///./test.db`` relativ zu ``/app`` und fand dort die mitgebackene
Datei vor — Tabellen eines abgebrochenen Laufs ueberleben ``create_all`` mit
altem Schema.

Geprueft wird zweierlei: die Reste sind ausgeschlossen, und nichts, was das
Image braucht (``app``, ``alembic``, ``tests`` samt Testdaten, die Skripte
und Konfigurationsdateien), faellt unter eine Regel. Die Regeln werden nach
der Semantik von Docker ausgewertet (moby/patternmatcher: Go-``filepath.Match``
mit ``**``, eine Regel auf ein Verzeichnis schliesst seinen Inhalt aus,
``!`` nimmt wieder auf, die letzte passende Regel gilt).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
DOCKERIGNORE = BACKEND / ".dockerignore"


def _to_regex(pattern: str) -> "re.Pattern[str]":
    out, i = "", 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if pattern[i:i + 2] == "**":
                i += 2
                if pattern[i:i + 1] == "/":
                    i += 1
                out += ".*" if i >= len(pattern) else "(.*/)?"
                continue
            out += "[^/]*"
        elif ch == "?":
            out += "[^/]"
        else:
            out += re.escape(ch)
        i += 1
    return re.compile("^" + out + "$")


def _rules():
    rules = []
    for raw in DOCKERIGNORE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        if negate:
            line = line[1:].strip()
        line = os.path.normpath(line.lstrip("/")).replace(os.sep, "/")
        rules.append((negate, _to_regex(line)))
    return rules


def _excluded(rel_path: str, rules) -> bool:
    parts = rel_path.split("/")
    prefixes = ["/".join(parts[:n]) for n in range(1, len(parts) + 1)]
    excluded = False
    for negate, rx in rules:
        if any(rx.match(p) for p in prefixes):
            excluded = not negate
    return excluded


@pytest.fixture(scope="module")
def rules():
    assert DOCKERIGNORE.is_file(), f"{DOCKERIGNORE} fehlt"
    return _rules()


# Je Regel mindestens ein Beispiel (test_jede_regel_hat_ein_beispiel). Der
# Docker-Bundle-Test in test_491_deploy_pull.py prueft dieselben Pfade gegen
# die tar-Ausschluesse von tools/build-release.sh — das Bundle liefert
# backend/ als Quelltext aus, dort duerfen die Reste ebenso wenig stehen.
HOST_RESTE = [
    "test.db",
    "test.db-wal",
    "test.db-shm",
    "test.db-journal",
    "__pycache__/create_test_data.cpython-312.pyc",
    "app/__pycache__/main.cpython-312.pyc",
    "app/services/__pycache__/calculation_service.cpython-312.pyc",
    "alembic/versions/__pycache__/073_work_blocks.cpython-312.pyc",
    "tests/__pycache__/conftest.cpython-312-pytest-8.4.1.pyc",
    "app/verirrt.pyc",
    "app/verirrt.pyo",
    ".pytest_cache/v/cache/lastfailed",
    ".mypy_cache/3.12/app/main.data.json",
    ".ruff_cache/0.6.9/1234567890",
    ".venv/bin/python",
    "venv/bin/python",
    ".coverage",
    "htmlcov/index.html",
    ".claude/agent-memory/notizen.md",
    ".env",
    ".env.local",
    "backups/praxiszeit_2026-10-17.sql",
]

BENOETIGT = [
    "Dockerfile",
    "requirements.txt",
    "alembic.ini",
    "pytest.ini",
    "init-db-user.sh",
    "init-db-user.sql",
    "create_handbuch_testdata.py",
    "create_test_data.py",
    "setup_extended_testdata.py",
    "fix_utc_times.py",
    "app/main.py",
    "app/routers/admin_backups.py",
    "alembic/env.py",
    "tests/conftest.py",
]


@pytest.mark.parametrize("path", HOST_RESTE)
def test_host_reste_bleiben_draussen(rules, path):
    assert _excluded(path, rules), path


@pytest.mark.parametrize("path", BENOETIGT)
def test_benoetigte_dateien_bleiben_drin(rules, path):
    assert not _excluded(path, rules), path


def test_jede_regel_hat_ein_beispiel(rules):
    """Eine neue Regel ohne Beispiel in HOST_RESTE wuerde weder hier noch im
    Docker-Bundle-Test (gleiche Liste) geprueft — das Bundle liesse den Rest
    dann unbemerkt durch (Gesamtreview B8)."""
    for negate, rx in rules:
        if negate:
            continue
        assert any(_excluded(p, [(False, rx)]) for p in HOST_RESTE), (
            f"Regel {rx.pattern} hat kein Beispiel in HOST_RESTE")


def test_kein_quelltext_und_keine_testdaten_werden_ausgeschlossen(rules):
    """Gegen den echten Baum: jede Datei unter app/, alembic/ und tests/
    (ausser Bytecode) muss im Image ankommen — auch Testdaten, Vorlagen und
    die Migrationen."""
    geprueft = 0
    for top in ("app", "alembic", "tests"):
        for dirpath, dirnames, filenames in os.walk(BACKEND / top):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if name.endswith((".pyc", ".pyo")):
                    continue
                rel = (Path(dirpath) / name).relative_to(BACKEND).as_posix()
                assert not _excluded(rel, rules), rel
                geprueft += 1
    assert geprueft > 100  # falscher Pfad darf kein „alles gut" ergeben


def test_matcher_folgt_der_docker_semantik():
    """Selbsttest des Nachbaus, damit die Tests oben nichts Falsches beweisen."""
    rx = _to_regex("**/__pycache__")
    assert rx.match("__pycache__") and rx.match("app/x/__pycache__")
    assert not rx.match("app/__pycache__x")
    assert _to_regex("test.db*").match("test.db-wal")
    assert not _to_regex("test.db*").match("tests/test.db")
    assert not _to_regex("*.pyc").match("app/x.pyc")  # * ueberquert kein /
    rules = [(False, _to_regex("backups")), (True, _to_regex("backups/keep.txt"))]
    assert _excluded("backups/a.sql", rules)  # Verzeichnisregel trifft den Inhalt
    assert not _excluded("backups/keep.txt", rules)  # ! nimmt wieder auf
