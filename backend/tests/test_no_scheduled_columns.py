"""Spec E23 / 17.6: nach Migration 073 liest kein Code mehr ``users.scheduled_*``.

Ein ``getattr(user, "scheduled_…", None)`` lieferte nach dem Spalten-Drop still
``None`` und schaltete die Kappung ab — deshalb ein Token-Guard statt
Vertrauen. In ``app/`` ist das Token verboten (die Altfeld-Erkennung nutzt nur
das Präfix ``scheduled_``, 11.4; die Migration liegt in ``alembic/``). In
``tests/`` sind nur LESEZUGRIFFE verboten — Tests dürfen die Altfelder als
JSON-Schlüssel senden (400-Tests). Ausgenommen: ``tests/test_073_*.py``
(Backfill/Downgrade lesen die Spalten per SQL) und dieser Guard.
"""
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP_TOKEN = re.compile(r"scheduled_(start|end)_")
TEST_READ = re.compile(r"\.scheduled_(start|end)_|getattr\([^)]*[\"']scheduled_")


def _py_files(root: Path):
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _hits(files, pattern):
    hits = []
    for path in files:
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(BACKEND)}:{no}: {line.strip()}")
    return hits


def test_app_has_no_scheduled_window_token():
    assert _hits(_py_files(BACKEND / "app"), APP_TOKEN) == []


def test_tests_do_not_read_scheduled_window_attributes():
    me = Path(__file__).name
    files = [p for p in _py_files(BACKEND / "tests")
             if p.name != me and not p.name.startswith("test_073_")]
    assert _hits(files, TEST_READ) == []
