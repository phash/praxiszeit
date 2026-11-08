"""Audit 2026-11-07 (#544): Konfiguration außerhalb von ``backend/``.

S2-1 PostgreSQL schreibt keine gescheiterten Statements (mit Werten) und kein
     DETAIL ins Server-Log: Docker-``db``-Kommando und die von
     ``praxiszeit-server.py`` erzeugte ``postgresql.conf``.
S2-9 Die nginx-Sperre für ``/api/metrics`` greift auch für tiefere Pfade.

Braucht das Repo-Wurzelverzeichnis und überspringt sich im reinen
Backend-Container (wie test_frontend_dockerignore.py); läuft in
``scripts/local-ci.sh`` Schritt 3.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"
SERVER = ROOT / "praxiszeit-server.py"
NGINX = [ROOT / "frontend" / "nginx.conf", ROOT / "ssl" / "nginx-ssl.conf"]

pytestmark = pytest.mark.skipif(not COMPOSE.exists(), reason="Repo-Wurzel nicht eingebunden")


def test_docker_db_does_not_log_failing_statements():
    text = COMPOSE.read_text(encoding="utf-8")
    db_block = text.split("\n  db:\n", 1)[1].split("\n  backend:\n", 1)[0]
    assert "log_min_error_statement=panic" in db_block
    assert "log_error_verbosity=terse" in db_block


def test_native_postgresql_conf_does_not_log_failing_statements():
    text = SERVER.read_text(encoding="utf-8")
    assert 'f.write("log_min_error_statement = panic\\n")' in text
    assert 'f.write("log_error_verbosity = terse\\n")' in text


@pytest.mark.parametrize("conf", NGINX, ids=lambda p: p.name)
def test_metrics_block_is_a_prefix_rule(conf):
    text = conf.read_text(encoding="utf-8")
    assert re.search(r"location\s+\^~\s+/api/metrics\s*\{", text), \
        "/api/metrics muss als ^~-Präfix gesperrt sein (sonst geht /api/metrics/ durch)"
    assert "location = /api/metrics" not in text
