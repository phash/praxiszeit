"""Der Handbuch-Seed darf nie ungewollt laufen (Schlussreview: Konten loeschen,
Admin umbenennen, oeffentliches Passwort). Ohne HANDBUCH_SEED=1 bricht er ab,
bevor er eine Datenbanksitzung oeffnet."""
import importlib.util
from pathlib import Path

import pytest

SEED_PATH = Path(__file__).resolve().parent.parent / "create_handbuch_testdata.py"


def _load():
    spec = importlib.util.spec_from_file_location("handbuch_seed_guard_under_test", SEED_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _no_session(*_a, **_k):
    raise AssertionError("Sitzung geoeffnet, obwohl der Schutz greifen muss")


@pytest.mark.parametrize("value", [None, "", "0", "true"])
def test_main_refuses_without_flag(monkeypatch, value):
    seed = _load()
    if value is None:
        monkeypatch.delenv("HANDBUCH_SEED", raising=False)
    else:
        monkeypatch.setenv("HANDBUCH_SEED", value)
    monkeypatch.setattr(seed, "SessionLocal", _no_session)
    with pytest.raises(SystemExit) as exc:
        seed.main(["--stichtag", "2026-03-11"])
    assert "HANDBUCH_SEED=1" in str(exc.value)


def test_print_stichtag_refuses_too(monkeypatch):
    seed = _load()
    monkeypatch.delenv("HANDBUCH_SEED", raising=False)
    monkeypatch.setattr(seed, "SessionLocal", _no_session)
    with pytest.raises(SystemExit):
        seed.main(["--print-stichtag"])


def test_seed_all_refuses_without_flag(monkeypatch):
    seed = _load()
    monkeypatch.delenv("HANDBUCH_SEED", raising=False)
    with pytest.raises(SystemExit):
        seed.seed_all(object(), seed.date(2026, 3, 11))


def test_flag_one_passes_the_guard(monkeypatch):
    seed = _load()
    monkeypatch.setenv("HANDBUCH_SEED", "1")
    seed.require_seed_flag()
