"""Nativer Sicherungspfad in ``praxiszeit-server.py`` (Kundenfall 2026-11-15,
Log-Audit der Windows-Installation, Punkte A4, A7, A11, A14, A15, A16, A19).

- A4: ``backup`` endet bei einem Fehlschlag mit Exitcode 2 (bisher 0, das
  Update lief trotzdem weiter).
- A7: nach jedem Lauf ``data/backups/.last-result.json`` (Vertrag mit Backend
  und Frontend-Banner), optionaler Spiegel ``[backup] mirror_dir``.
- A11: von NSSM rotierte Dienstlogs verfallen nach ``[logs] retention_days``.
- A14: ``backup --label``; die letzten drei ``preupdate*``-Sicherungen bleiben.
- A15: jede Sicherung wird nach dem Schreiben zurueckgelesen.
- A16: verwalteter Log-Block in postgresql.conf, application_name in den URLs.
- A19: fehlende Leserechte auf .db-credentials -> deutscher Hinweis, Exit 1.
"""
import argparse
import gzip
import importlib.util
import io
import json
import logging
import os
import time
from pathlib import Path

import pytest

_SERVER_PATH = Path(__file__).resolve().parents[2] / "praxiszeit-server.py"

pytestmark = pytest.mark.skipif(
    not _SERVER_PATH.exists(),
    reason=f"praxiszeit-server.py not reachable at {_SERVER_PATH}",
)

_KEY = "k" * 64
_DUMP = (
    b"--\n-- PostgreSQL database dump\n--\n\nCREATE TABLE t ();\n"
    + b"-- fuellzeile\n" * 200
    + b"--\n-- PostgreSQL database dump complete\n--\n\n"
)


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("praxiszeit_server_backup", _SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _fresh_pg_port(srv):
    srv.pg_port.cache_clear()
    yield
    srv.pg_port.cache_clear()


def _fake_popen(payload: bytes, rc: int = 0):
    class _P:
        calls = []

        def __init__(self, argv, *a, **kw):
            _P.calls.append((argv, kw))
            self.stdout = io.BytesIO(payload)
            self.returncode = rc

        def wait(self):
            return rc

    return _P


@pytest.fixture
def inst(srv, tmp_path, monkeypatch):
    backups = tmp_path / "data" / "backups"
    backups.mkdir(parents=True)
    monkeypatch.setattr(srv, "BASE_DIR", tmp_path)
    monkeypatch.setattr(srv, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(srv, "BACKUP_DIR", backups)
    monkeypatch.setattr(srv, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(srv, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(srv, "IS_WINDOWS", False)
    monkeypatch.setattr(srv, "pg_load_credentials", lambda: ("su-pw", "app-pw"))
    monkeypatch.setattr(srv, "pg_cmd", lambda name: Path("/x") / name)
    monkeypatch.setattr(srv, "load_config", lambda: {})
    monkeypatch.delenv("BACKUP_MIRROR_DIR", raising=False)
    monkeypatch.setattr(srv.subprocess, "Popen", _fake_popen(_DUMP))
    return tmp_path


def _status(inst):
    return json.loads((inst / "data" / "backups" / ".last-result.json").read_text(encoding="utf-8"))


def _cfg(**backup):
    return {"security": {"secret_key": _KEY}, "backup": backup}


# --- A4: Exitcode ------------------------------------------------------------

def test_cmd_backup_endet_mit_2_wenn_die_sicherung_scheitert(srv, inst, monkeypatch):
    monkeypatch.setattr(srv, "pg_cluster_state", lambda: "own")
    monkeypatch.setattr(srv, "create_backup", lambda config, label=None: None)
    with pytest.raises(SystemExit) as e:
        srv.cmd_backup(argparse.Namespace(label=None))
    assert e.value.code == 2


def test_cmd_backup_ohne_fehler_endet_normal(srv, inst, monkeypatch):
    monkeypatch.setattr(srv, "pg_cluster_state", lambda: "own")
    seen = {}
    monkeypatch.setattr(srv, "create_backup",
                        lambda config, label=None: seen.setdefault("label", label) or Path("x"))
    srv.cmd_backup(argparse.Namespace(label="preupdate-1.24.0-1.24.1"))
    assert seen["label"] == "preupdate-1.24.0-1.24.1"


def test_cmd_backup_ohne_laufendes_postgresql_schreibt_den_status(srv, inst, monkeypatch):
    monkeypatch.setattr(srv, "pg_cluster_state", lambda: "down")
    with pytest.raises(SystemExit) as e:
        srv.cmd_backup(argparse.Namespace(label=None))
    assert e.value.code == 1
    st = _status(inst)
    assert st["ok"] is False and "PostgreSQL" in st["error"]


def test_cmd_backup_ohne_leserechte_zeigt_den_adminhinweis_zuerst(srv, inst, monkeypatch, caplog):
    """Review-Fund zu A19 (Kundenfall 2026-11-15): backup.bat ohne Adminrechte
    scheiterte unter Windows schon an ``pg_ctl status`` (kein Lesezugriff auf
    data\\postgresql) und meldete "PostgreSQL is not running" — samt falschem
    Status fuer das Admin-Banner. Die Rechtepruefung kommt jetzt zuerst."""
    cfg = inst / "config"
    cfg.mkdir()
    (cfg / ".db-credentials").write_text("SUPERUSER_PASSWORD=x\n", encoding="utf-8")

    def _deny(self, *a, **k):
        raise PermissionError(13, "Zugriff verweigert")

    def _nie(*a, **k):
        raise AssertionError("pg_cluster_state darf ohne Leserechte nicht laufen")

    monkeypatch.setattr(Path, "read_text", _deny)
    monkeypatch.setattr(srv, "pg_cluster_state", _nie)
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        with pytest.raises(SystemExit) as e:
            srv.cmd_backup(argparse.Namespace(label=None))
    assert e.value.code == 1
    assert "Administrator" in caplog.text
    monkeypatch.undo()
    assert not (inst / "data" / "backups" / ".last-result.json").exists()


def test_cmd_backup_unklarer_zustand_schreibt_keinen_status(srv, inst, monkeypatch, caplog):
    """``unknown`` (pg_ctl ohne Leserechte, Zeitgrenze, Server faehrt hoch) ist
    kein Beleg fuer "PostgreSQL laeuft nicht": kein Fehlerstatus, der im
    Admin-Banner landet, aber Exit 1 mit Hinweis."""
    monkeypatch.setattr(srv, "pg_cluster_state", lambda: "unknown")
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        with pytest.raises(SystemExit) as e:
            srv.cmd_backup(argparse.Namespace(label=None))
    assert e.value.code == 1
    assert "Administrator" in caplog.text
    assert not (inst / "data" / "backups" / ".last-result.json").exists()


def test_backup_kennt_die_option_label(srv):
    import subprocess
    import sys
    out = subprocess.run([sys.executable, str(_SERVER_PATH), "backup", "--help"],
                         capture_output=True, text=True)
    assert "--label" in out.stdout


# --- A7: Statusdatei ----------------------------------------------------------

def test_erfolg_schreibt_die_statusdatei(srv, inst):
    path = srv.create_backup(_cfg())
    assert path is not None and path.exists()
    st = _status(inst)
    assert set(st) == {"ok", "finished_at", "file", "size_bytes", "error", "mirror_ok", "verified"}
    assert st["ok"] is True and st["error"] is None
    assert st["file"] == path.name
    assert st["size_bytes"] == path.stat().st_size
    assert st["mirror_ok"] is None
    assert st["verified"] is True
    from datetime import datetime
    assert datetime.fromisoformat(st["finished_at"]).utcoffset() is not None
    # atomar geschrieben: keine Temp-Datei bleibt liegen
    assert [p.name for p in (inst / "data" / "backups").iterdir()
            if p.name.startswith(".last-result") and p.name != ".last-result.json"] == []


def test_fehler_von_pg_dump_schreibt_die_statusdatei(srv, inst, monkeypatch):
    monkeypatch.setattr(srv.subprocess, "Popen", _fake_popen(b"", rc=1))
    assert srv.create_backup(_cfg()) is None
    st = _status(inst)
    assert st["ok"] is False and st["file"] is None and st["verified"] is False
    assert "pg_dump" in st["error"]


def test_ohne_zugangsdaten_schreibt_die_statusdatei(srv, inst, monkeypatch):
    monkeypatch.setattr(srv, "pg_load_credentials", lambda: (None, None))
    assert srv.create_backup(_cfg()) is None
    assert _status(inst)["ok"] is False


def test_pg_dump_traegt_application_name(srv, inst):
    srv.create_backup(_cfg())
    _, kw = srv.subprocess.Popen.calls[-1]
    assert kw["env"]["PGAPPNAME"] == "praxiszeit-backup"


def test_spiegel_bekommt_eine_kopie(srv, inst):
    mirror = inst / "usb"
    mirror.mkdir()
    path = srv.create_backup(_cfg(mirror_dir=str(mirror)))
    assert (mirror / path.name).read_bytes() == path.read_bytes()
    assert _status(inst)["mirror_ok"] is True


def test_spiegel_relativ_zur_installation_und_per_umgebung(srv, inst, monkeypatch):
    (inst / "spiegel").mkdir()
    monkeypatch.setenv("BACKUP_MIRROR_DIR", "spiegel")
    path = srv.create_backup(_cfg(mirror_dir="/gibt/es/nicht"))
    assert (inst / "spiegel" / path.name).exists()


def test_fehlender_spiegel_laesst_die_sicherung_gelten(srv, inst, caplog):
    with caplog.at_level(logging.WARNING, logger="praxiszeit"):
        path = srv.create_backup(_cfg(mirror_dir=str(inst / "fehlt" / "ziel")))
    assert path is not None and path.exists()
    st = _status(inst)
    assert st["ok"] is True and st["mirror_ok"] is False
    assert "Spiegel" in caplog.text
    assert not (inst / "fehlt").exists()  # nie einen ganzen Pfad anlegen


# --- A14: Bezeichnung + Aufbewahrung -----------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("preupdate-1.21.1-1.24.0", "preupdate-1.21.1-1.24.0"),
    ("Pre Update/1.2", "pre-update-1.2"),
    ("..x..", "x"),
    ("ÄÖÜ", None),
    ("", None),
    (None, None),
    ("a" * 80, "a" * 40),
])
def test_bezeichnung_wird_bereinigt(srv, raw, expected):
    assert srv.sanitize_backup_label(raw) == expected


def test_sicherung_mit_bezeichnung(srv, inst):
    path = srv.create_backup(_cfg(), label="PreUpdate-1.24.0-1.24.1")
    assert path.name.startswith("praxiszeit_")
    assert path.name.endswith("_preupdate-1.24.0-1.24.1.sql.gz")
    assert _status(inst)["file"] == path.name


def _old(path: Path, days: float, data: bytes = b"x" * 50):
    path.write_bytes(data)
    t = time.time() - days * 86400
    os.utime(path, (t, t))
    return path


def test_aufbewahrung_haelt_die_letzten_drei_preupdate_sicherungen(srv, inst):
    b = inst / "data" / "backups"
    pre = [_old(b / f"praxiszeit_2026010{i}_120000_preupdate-1.{i}.0-1.{i}.1.sql.gz", 100 - i)
           for i in range(1, 6)]
    plain_old = _old(b / "praxiszeit_20260101_000000.sql.gz", 90)
    other_label = _old(b / "praxiszeit_20260102_000000_manuell.sql.gz", 90)
    plain_new = _old(b / "praxiszeit_20261110_000000.sql.gz", 2)
    srv.create_backup(_cfg(retention_days=31))
    assert [p.exists() for p in pre] == [False, False, True, True, True]
    assert not plain_old.exists() and not other_label.exists()
    assert plain_new.exists()


def test_aufbewahrung_gilt_auch_im_spiegel(srv, inst):
    mirror = inst / "usb"
    mirror.mkdir()
    gone = _old(mirror / "praxiszeit_20260101_000000.sql.gz", 90)
    kept = _old(mirror / "praxiszeit_20260101_000000_preupdate-a.sql.gz", 90)
    srv.create_backup(_cfg(mirror_dir=str(mirror), retention_days=31))
    assert not gone.exists() and kept.exists()


# --- A15: Zuruecklesen --------------------------------------------------------

def test_fehlende_schlusszeile_ist_ein_fehlschlag(srv, inst, monkeypatch):
    monkeypatch.setattr(srv.subprocess, "Popen", _fake_popen(b"-- abgebrochen\n" * 50))
    assert srv.create_backup(_cfg()) is None
    st = _status(inst)
    assert st["ok"] is False and st["verified"] is False
    assert "Schlusszeile" in st["error"]


def test_pruefung_erkennt_eine_falsche_signatur(srv, tmp_path):
    p = tmp_path / "b.sql.gz"
    with gzip.open(p, "wb") as gz:
        gz.write(_DUMP + b"-- praxiszeit-backup-hmac-v1 " + b"0" * 64 + b"\n")
    ok, err = srv.verify_backup_file(p, _KEY)
    assert ok is False and "Signatur" in err


def test_pruefung_erkennt_ein_kaputtes_archiv(srv, tmp_path):
    p = tmp_path / "b.sql.gz"
    p.write_bytes(gzip.compress(_DUMP)[:-30])
    ok, err = srv.verify_backup_file(p, _KEY)
    assert ok is False and err


def test_pruefung_ohne_schluessel_prueft_nur_die_schlusszeile(srv, tmp_path):
    p = tmp_path / "b.sql.gz"
    p.write_bytes(gzip.compress(_DUMP))
    assert srv.verify_backup_file(p, None) == (True, None)


def test_groessenverlust_wird_gemeldet(srv, inst, caplog):
    b = inst / "data" / "backups"
    _old(b / "praxiszeit_20261101_000000.sql.gz", 1, os.urandom(200_000))
    with caplog.at_level(logging.WARNING, logger="praxiszeit"):
        assert srv.create_backup(_cfg()) is not None
    assert "kleiner" in caplog.text


def test_kein_hinweis_ohne_groessenverlust(srv, inst, caplog):
    with caplog.at_level(logging.WARNING, logger="praxiszeit"):
        srv.create_backup(_cfg())
    assert "kleiner" not in caplog.text


# --- A11: rotierte Dienstlogs -------------------------------------------------

def test_alte_rotierte_dienstlogs_werden_geloescht(srv, tmp_path, caplog):
    old_out = _old(tmp_path / "service-stdout-20260407T101010.123.log", 40)
    old_err = _old(tmp_path / "service-stderr-20260407T101010.123.log", 40)
    new_err = _old(tmp_path / "service-stderr-20261110T101010.123.log", 5)
    active = _old(tmp_path / "service-stderr.log", 400)
    other = _old(tmp_path / "praxiszeit.log", 400)
    with caplog.at_level(logging.INFO, logger="praxiszeit"):
        removed = srv.cleanup_rotated_service_logs({}, log_dir=tmp_path)
    assert sorted(removed) == sorted([old_out.name, old_err.name])
    assert not old_out.exists() and not old_err.exists()
    assert new_err.exists() and active.exists() and other.exists()
    assert old_out.name in caplog.text


def test_aufbewahrung_der_dienstlogs_ist_einstellbar(srv, tmp_path):
    f = _old(tmp_path / "service-stdout-20261101T000000.000.log", 10)
    srv.cleanup_rotated_service_logs({"logs": {"retention_days": 7}}, log_dir=tmp_path)
    assert not f.exists()


def test_aufbewahrung_null_schaltet_ab(srv, tmp_path):
    f = _old(tmp_path / "service-stdout-20260101T000000.000.log", 300)
    assert srv.cleanup_rotated_service_logs({"logs": {"retention_days": 0}},
                                            log_dir=tmp_path) == []
    assert f.exists()


def test_ungueltige_aufbewahrung_nimmt_die_vorgabe(srv, tmp_path, caplog):
    f = _old(tmp_path / "service-stdout-20260101T000000.000.log", 40)
    with caplog.at_level(logging.WARNING, logger="praxiszeit"):
        srv.cleanup_rotated_service_logs({"logs": {"retention_days": "viel"}}, log_dir=tmp_path)
    assert not f.exists()
    assert "retention_days" in caplog.text


def test_altes_postgresql_log_verfaellt_ebenfalls(srv, tmp_path):
    """Seit dem Wochenring (A16) wird postgresql.log nicht mehr geschrieben."""
    f = _old(tmp_path / "postgresql.log", 40)
    srv.cleanup_rotated_service_logs({}, log_dir=tmp_path)
    assert not f.exists()


def test_fehlendes_logverzeichnis_ist_kein_fehler(srv, tmp_path):
    assert srv.cleanup_rotated_service_logs({}, log_dir=tmp_path / "fehlt") == []


# --- A16: PostgreSQL-Logring + application_name ------------------------------

_CONF = "# initdb\nmax_connections = 100\n\n# PraxisZeit configuration\nport = 5432\n" \
        "log_filename = 'postgresql.log'\nlog_rotation_age = 1d\n"


def test_logblock_wird_angehaengt_und_ist_idempotent(srv, tmp_path):
    conf = tmp_path / "postgresql.conf"
    conf.write_text(_CONF, encoding="utf-8")
    assert srv.sync_managed_pg_logging(conf) is True
    text = conf.read_text(encoding="utf-8")
    assert text.startswith(_CONF)
    block = text[len(_CONF):]
    assert "log_filename = 'postgresql-%a.log'" in block
    assert "log_truncate_on_rotation = on" in block
    assert "log_rotation_age = 1d" in block
    assert "%u@%d" in block and "%a" in block.split("log_line_prefix")[1]
    assert srv.sync_managed_pg_logging(conf) is False
    assert conf.read_text(encoding="utf-8") == text


def test_veralteter_logblock_wird_ersetzt(srv, tmp_path):
    conf = tmp_path / "postgresql.conf"
    conf.write_text(_CONF, encoding="utf-8")
    srv.sync_managed_pg_logging(conf)
    good = conf.read_text(encoding="utf-8")
    conf.write_text(good.replace("postgresql-%a.log", "alt.log") + "work_mem = 4MB\n",
                    encoding="utf-8")
    assert srv.sync_managed_pg_logging(conf) is True
    text = conf.read_text(encoding="utf-8")
    assert "alt.log" not in text and text.count("postgresql-%a.log") == 1
    # Block steht am Ende (letzte Zeile gewinnt in postgresql.conf)
    assert text.rstrip().splitlines()[-1] == srv.PG_LOG_BLOCK_END


def test_logblock_behaelt_crlf(srv, tmp_path):
    conf = tmp_path / "postgresql.conf"
    conf.write_bytes(_CONF.replace("\n", "\r\n").encode("utf-8"))
    srv.sync_managed_pg_logging(conf)
    raw = conf.read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n")


def test_database_url_mit_application_name_windows(srv, monkeypatch):
    monkeypatch.setattr(srv, "IS_WINDOWS", True)
    monkeypatch.setattr(srv, "load_config", lambda: {})
    url = srv._database_url("u", "pw", "praxiszeit", application_name="praxiszeit-app")
    assert url.endswith("?require_auth=scram-sha-256&application_name=praxiszeit-app")
    from sqlalchemy.engine import make_url
    assert make_url(url).query["application_name"] == "praxiszeit-app"


def test_database_url_mit_application_name_unix(srv, tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "IS_WINDOWS", False)
    monkeypatch.setattr(srv, "DATA_DIR", tmp_path)
    url = srv._database_url("u", "pw", "praxiszeit", application_name="praxiszeit-migrate")
    assert url.endswith("&application_name=praxiszeit-migrate")
    assert "?host=" in url


def test_database_url_ohne_application_name_unveraendert(srv, monkeypatch):
    monkeypatch.setattr(srv, "IS_WINDOWS", True)
    monkeypatch.setattr(srv, "load_config", lambda: {})
    assert "application_name" not in srv._database_url("u", "pw", "praxiszeit")


def test_startprotokoll_liest_den_wochentagsring(srv, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(srv, "LOG_DIR", tmp_path)
    _old(tmp_path / "postgresql-Mon.log", 3, b"alt\n")
    (tmp_path / "postgresql-Sun.log").write_text("FATAL: ring\n", encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        assert srv._dump_pg_startup_log(since=time.time() - 5) is True
    assert "FATAL: ring" in caplog.text


# --- A19: Rechte auf .db-credentials -----------------------------------------

def test_fehlende_leserechte_ergeben_einen_hinweis(srv, tmp_path, monkeypatch, caplog):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / ".db-credentials").write_text("SUPERUSER_PASSWORD=x\n", encoding="utf-8")
    monkeypatch.setattr(srv, "CONFIG_DIR", cfg)

    def _deny(self, *a, **k):
        raise PermissionError(13, "Zugriff verweigert")

    monkeypatch.setattr(Path, "read_text", _deny)
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        with pytest.raises(SystemExit) as e:
            srv.pg_load_credentials()
    assert e.value.code == 1
    assert "Administrator" in caplog.text
    assert "Traceback" not in caplog.text


# --- A16 Nachtrag: Wochenring auch bei taeglich ausgeschaltetem PC ------------
# Review-Fund (Kundenfall 2026-11-15): PostgreSQL leert eine Ringdatei nur bei
# der Zeitrotation um Mitternacht, nie beim Start. Der Praxis-PC laeuft nachts
# nicht, der PostgreSQL-Dienst (Starttyp auto) oeffnet die Datei des Tages beim
# Hochfahren im Anhaengemodus — ohne Nachhilfe wuechse jede Datei endlos.

def _ring_at(tmp_path, name, days_ago, now):
    f = tmp_path / name
    f.write_bytes(b"alte Zeilen\n" * 10)
    t = now - days_ago * 86400
    os.utime(f, (t, t))
    return f


def test_ring_leert_dateien_ab_sechs_tagen(srv, tmp_path):
    import datetime as dt
    now = dt.datetime(2026, 11, 16, 8, 0).timestamp()  # Montag 08:00
    morgen = _ring_at(tmp_path, "postgresql-Tue.log", 6 - 0.4, now)   # Di. vor 6 Tagen, 17:36
    gestern = _ring_at(tmp_path, "postgresql-Sun.log", 1, now)
    heute_alt = _ring_at(tmp_path, "postgresql-Mon.log", 7, now)
    fremd = _ring_at(tmp_path, "postgresql-alt.log", 30, now)
    geleert = srv.reset_stale_pg_ring_logs(log_dir=tmp_path, now=now)
    assert sorted(geleert) == ["postgresql-Mon.log", "postgresql-Tue.log"]
    assert morgen.stat().st_size == 0 and heute_alt.stat().st_size == 0
    assert gestern.stat().st_size > 0
    assert fremd.stat().st_size > 0  # nur der Ring, keine anderen Dateien
    assert morgen.exists() and heute_alt.exists()  # geleert, nicht geloescht (ACL bleibt)


def test_ring_laesst_die_heutige_datei_stehen(srv, tmp_path):
    import datetime as dt
    now = dt.datetime(2026, 11, 16, 8, 0).timestamp()
    heute = _ring_at(tmp_path, "postgresql-Mon.log", 0.01, now)
    fuenf = _ring_at(tmp_path, "postgresql-Wed.log", 5, now)
    assert srv.reset_stale_pg_ring_logs(log_dir=tmp_path, now=now) == []
    assert heute.stat().st_size > 0 and fuenf.stat().st_size > 0


def test_ring_ohne_logverzeichnis(srv, tmp_path):
    assert srv.reset_stale_pg_ring_logs(log_dir=tmp_path / "fehlt") == []


def test_ring_schreibfehler_blockiert_nichts(srv, tmp_path, monkeypatch, caplog):
    import builtins
    import datetime as dt
    now = dt.datetime(2026, 11, 16, 8, 0).timestamp()
    _ring_at(tmp_path, "postgresql-Mon.log", 7, now)
    real_open = builtins.open

    def _open(file, mode="r", *a, **k):
        if str(file).endswith("postgresql-Mon.log") and "+" in mode:
            raise PermissionError(13, "gesperrt")
        return real_open(file, mode, *a, **k)

    monkeypatch.setattr(builtins, "open", _open)
    with caplog.at_level(logging.WARNING, logger="praxiszeit"):
        assert srv.reset_stale_pg_ring_logs(log_dir=tmp_path, now=now) == []
    assert "postgresql-Mon.log" in caplog.text
