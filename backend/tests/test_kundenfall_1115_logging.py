"""Kundenfall 2026-11-15, Log-Audit Punkte 8 (NET-1) und 17 (NET-3).

8: AUTH-Zeilen des Loggers ``praxiszeit.security`` standen ohne Uhrzeit und
ohne IP in stderr (kein eigener Handler → ``logging.lastResort``). Jetzt ein
eigener Handler mit Zeitstempel und ``ip=`` (IP aus einer ContextVar, die eine
ASGI-Middleware je Anfrage setzt) — idempotent, keine doppelten Zeilen.

17: Polling macht 86 % des Access-Logs aus. Ein Filter auf ``uvicorn.access``
verwirft nur die 2xx-Zeilen der drei Polling-Endpunkte; Fehler bleiben.
"""
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import log_setup


def _access_record(path, status):
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d', ("1.2.3.4:5555", "GET", path, "1.1", status), None,
    )


def test_access_filter_drops_2xx_polling_lines():
    f = log_setup.PollingAccessLogFilter()
    assert f.filter(_access_record("/api/time-entries/clock-status", 200)) is False
    assert f.filter(_access_record("/api/admin/change-requests/pending-count", 200)) is False
    assert f.filter(_access_record("/api/admin/vacation-requests/pending-count?x=1", 204)) is False
    assert f.filter(_access_record("/api/admin/vacation-requests/pending-count/", 200)) is False


def test_access_filter_keeps_errors_and_other_paths():
    f = log_setup.PollingAccessLogFilter()
    assert f.filter(_access_record("/api/time-entries/clock-status", 401)) is True
    assert f.filter(_access_record("/api/time-entries/clock-status", 500)) is True
    assert f.filter(_access_record("/api/time-entries/clock-status", 307)) is True
    assert f.filter(_access_record("/api/time-entries", 200)) is True
    # Unerwartete Form (andere uvicorn-Version): nie verschlucken.
    odd = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, "plain", None, None)
    assert f.filter(odd) is True


def test_install_access_filter_is_idempotent():
    log_setup.install_access_log_filter()
    log_setup.install_access_log_filter()
    lg = logging.getLogger("uvicorn.access")
    assert sum(isinstance(x, log_setup.PollingAccessLogFilter) for x in lg.filters) == 1


def test_security_handler_installed_once_with_timestamp_and_ip():
    log_setup.install_security_log_handler()
    log_setup.install_security_log_handler()
    lg = logging.getLogger("praxiszeit.security")
    own = [h for h in lg.handlers if getattr(h, log_setup._MARKER, False)]
    assert len(own) == 1
    assert lg.level == logging.INFO
    rec = logging.LogRecord("praxiszeit.security", logging.WARNING, __file__, 1,
                            "AUTH login_failed user=%s", ("x",), None)
    token = log_setup.client_ip_var.set("10.0.0.7")
    try:
        for flt in lg.filters:
            flt.filter(rec)
    finally:
        log_setup.client_ip_var.reset(token)
    line = own[0].format(rec)
    assert "AUTH login_failed user=x" in line
    assert "ip=10.0.0.7" in line
    # asctime vorn: Datum im Format JJJJ-MM-TT
    assert line[:4].isdigit() and line[4] == "-"


def test_client_ip_reaches_sync_endpoint_via_middleware(caplog):
    log_setup.install_security_log_handler()
    a = FastAPI()
    a.add_middleware(log_setup.ClientIpContextMiddleware)

    @a.get("/x")
    def x():
        logging.getLogger("praxiszeit.security").warning("AUTH probe")
        return {}

    with caplog.at_level(logging.WARNING, logger="praxiszeit.security"):
        TestClient(a).get("/x")
    recs = [r for r in caplog.records if r.getMessage() == "AUTH probe"]
    assert recs and recs[0].client_ip == "testclient"
    # ausserhalb einer Anfrage: "-"
    assert log_setup.client_ip_var.get() == "-"


def test_security_lines_once_under_native_uvicorn_log_config(capsys):
    """Review-Fund: nativ gibt ``uvicorn_log_config()`` (praxiszeit-server.py,
    ``--log-config``) der Wurzel einen stderr-Handler. Jede AUTH-Zeile (WARNING
    und INFO) muss trotzdem genau EINMAL in service-stderr.log stehen."""
    import importlib.util
    import logging.config
    from pathlib import Path

    import pytest

    server_path = Path(__file__).resolve().parents[2] / "praxiszeit-server.py"
    if not server_path.exists():
        pytest.skip(f"praxiszeit-server.py not reachable at {server_path}")
    spec = importlib.util.spec_from_file_location("praxiszeit_server_logcfg", server_path)
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)

    root = logging.getLogger()
    sec = logging.getLogger("praxiszeit.security")
    names = ("uvicorn", "uvicorn.error", "uvicorn.access")
    saved_root = (root.handlers[:], root.level)
    saved_sec = (sec.handlers[:], sec.propagate, sec.level)
    saved_uv = {n: (logging.getLogger(n).handlers[:], logging.getLogger(n).propagate,
                    logging.getLogger(n).level) for n in names}
    try:
        # Zustand wie im nativen Dienst: keine Test-Weiterleitung, frischer Handler.
        sec.handlers = []
        logging.config.dictConfig(srv.uvicorn_log_config())
        log_setup.install_security_log_handler()
        sec.warning("AUTH login_failed user=%s reason=%s", "probe-w", "bad_password")
        sec.info("AUTH login_success user=%s", "probe-i")
        err = capsys.readouterr().err
    finally:
        root.handlers, root.level = saved_root
        sec.handlers, sec.propagate, sec.level = saved_sec
        for n, (h, p, lvl) in saved_uv.items():
            lgr = logging.getLogger(n)
            lgr.handlers, lgr.propagate, lgr.level = h, p, lvl
    w_lines = [ln for ln in err.splitlines() if "probe-w" in ln]
    i_lines = [ln for ln in err.splitlines() if "probe-i" in ln]
    assert len(w_lines) == 1, err
    assert len(i_lines) == 1, err
    assert "ip=" in w_lines[0]
