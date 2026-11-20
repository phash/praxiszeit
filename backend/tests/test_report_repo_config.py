"""mrd-report-1 (#557): Einstellungen außerhalb von ``backend/`` — Compose,
Beispielkonfigurationen und ``_CONF_TO_ENV`` des nativen Prozessmanagers.

Braucht das Repo-Wurzelverzeichnis und überspringt sich im reinen
Backend-Container; läuft in ``scripts/local-ci.sh`` Schritt 3.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

KEY = "mrk_praxiszeit_Zufall123abc"
_ROOT = Path(__file__).resolve().parents[2]
_SERVER = _ROOT / "praxiszeit-server.py"

pytestmark = pytest.mark.skipif(not _SERVER.exists(), reason="Repo-Wurzel nicht eingebunden")


def test_compose_passes_report_settings_to_backend():
    for compose in _ROOT.glob("docker-compose*.yml"):
        text = compose.read_text(encoding="utf-8")
        if "PRACTICE_ADDRESS:" not in text:
            continue
        assert "FEEDBACK_REPORT_KEY: ${FEEDBACK_REPORT_KEY:-}" in text, compose.name
        assert ("FEEDBACK_REPORT_BASE_URL: ${FEEDBACK_REPORT_BASE_URL:-https://report.mr-development.de}"
                in text), compose.name


def test_examples_document_feedback_block():
    env = (_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "# FEEDBACK_REPORT_KEY=" in env
    conf = (_ROOT / "installer" / "praxiszeit.conf.example").read_text(encoding="utf-8")
    assert "# [feedback]" in conf and "# report_key = " in conf
    import tomllib
    assert "feedback" not in tomllib.loads(conf)  # nur kommentiert


def test_native_conf_maps_feedback_keys_to_env():
    spec = importlib.util.spec_from_file_location("praxiszeit_server_report", _SERVER)
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)
    assert srv._CONF_TO_ENV[("feedback", "report_key")] == "FEEDBACK_REPORT_KEY"
    assert srv._CONF_TO_ENV[("feedback", "report_base_url")] == "FEEDBACK_REPORT_BASE_URL"
    env = {}
    srv.apply_config_env({"feedback": {"report_key": KEY,
                                       "report_base_url": "https://report.mr-development.de"}}, env)
    assert env["FEEDBACK_REPORT_KEY"] == KEY
    assert env["FEEDBACK_REPORT_BASE_URL"] == "https://report.mr-development.de"
