"""Log-Audit Kundenfall 2026-11-15 (native Windows-Installation): Prozessmanager.

Abgedeckt (Punkte aus der Log-Auswertung):

* A2 — Restfenster nach Fix (a): uvicorn sieht das Ctrl+C von NSSM vor dem
  Manager und beendet sich sauber; der Wachhund darf dann nicht neu starten.
* A6 — PostgreSQL-Startfehler unter Windows diagnostizierbar machen
  (net-start-Ausgabe, sc queryex, nur frische Logdateien, Eventlog).
* A8 — uvicorn- und App-Meldungen in service-stderr/stdout mit Uhrzeit.
* A9 — PostgreSQL-Wachhund gegen das Herunterfahren von Windows.
* D/NET-8 — ``[server] allowed_hosts`` aus praxiszeit.conf.
* F-054 — die Gesundheitspruefung spricht dasselbe Protokoll wie uvicorn.

Geladen per importlib wie test_native_pg_lifecycle.py.
"""
import importlib.util
import json
import logging
import logging.config
import os
import time
import types
from pathlib import Path

import pytest

_SERVER_PATH = Path(__file__).resolve().parents[2] / "praxiszeit-server.py"

pytestmark = pytest.mark.skipif(
    not _SERVER_PATH.exists(),
    reason=f"praxiszeit-server.py not reachable at {_SERVER_PATH}",
)


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("praxiszeit_server_logaudit", _SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _fresh_state(srv):
    srv.pg_port.cache_clear()
    srv._watchdog_foreign_streak = 0
    srv._watchdog_down_streak = 0
    yield
    srv.pg_port.cache_clear()
    srv._watchdog_foreign_streak = 0
    srv._watchdog_down_streak = 0


def _result(rc=0, stdout="", stderr=""):
    return types.SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr)


# --- A2: Stoppwunsch nach dem Ende von uvicorn abwarten -----------------------

class TestStoppNachKindende:
    """Kundenfall 2026-11-15 / Log-Audit A2: In drei Faellen beendete sich
    uvicorn sauber ("Finished server process", Exitcode 0 bzw. 3), bevor der
    Manager das Ctrl+C protokolliert hatte — der Python-Signalhandler laeuft erst,
    wenn der Hauptthread aus einem blockierenden Aufruf (pg_isready) zurueck ist.
    """

    @pytest.mark.parametrize("rc", [0, 3, 0xC000013A, -1073741510])
    def test_verzoegerter_stoppwunsch_verhindert_neustart(self, srv, rc):
        geschlafen = []
        stopp = {"jetzt": False}

        def sleeper(s):
            geschlafen.append(s)
            if len(geschlafen) == 3:  # Signal kommt ~1,5 s nach dem Kindende
                stopp["jetzt"] = True

        assert srv.stop_follows_child_exit(rc, lambda: stopp["jetzt"], sleeper=sleeper) is True
        assert sum(geschlafen) <= srv.CHILD_EXIT_STOP_GRACE_SECONDS

    def test_ohne_stoppwunsch_wird_nach_der_frist_neu_gestartet(self, srv):
        geschlafen = []
        assert srv.stop_follows_child_exit(0, lambda: False, sleeper=geschlafen.append) is False
        assert sum(geschlafen) == pytest.approx(srv.CHILD_EXIT_STOP_GRACE_SECONDS)
        assert 2.0 <= srv.CHILD_EXIT_STOP_GRACE_SECONDS <= 5.0

    def test_absturzcode_wartet_nicht(self, srv):
        """Exitcode 1 (Absturz, Konfigurationsfehler) ist kein Ctrl+C-Ende —
        kein Warten, der Neustart kommt sofort."""
        geschlafen = []
        assert srv.stop_follows_child_exit(1, lambda: False, sleeper=geschlafen.append) is False
        assert geschlafen == []

    def test_bereits_gewuenschter_stopp_gilt_auch_bei_absturzcode(self, srv):
        assert srv.stop_follows_child_exit(1, lambda: True, sleeper=lambda s: None) is True


# --- A9: Windows-Dienstzustand ------------------------------------------------

_SC_DE_STOP_PENDING = (
    "\r\nDIENSTNAME: PraxisZeit-PostgreSQL\r\n"
    "        TYP                : 10  WIN32_OWN_PROCESS\r\n"
    "        STATUS             : 3  STOP_PENDING\r\n"
    "                                (STOPPABLE, NOT_PAUSABLE, ACCEPTS_SHUTDOWN)\r\n"
    "        WIN32_EXITCODE     : 0  (0x0)\r\n"
)
_SC_EN_RUNNING = (
    "SERVICE_NAME: PraxisZeit-PostgreSQL\n"
    "        TYPE               : 10  WIN32_OWN_PROCESS\n"
    "        STATE              : 4  RUNNING\n"
)


class TestWindowsDienstzustand:
    def test_1060_heisst_fehlt(self, srv):
        runner = lambda argv, **kw: _result(1060, "FEHLER 1060")  # noqa: E731
        assert srv._win_service_state("X", runner=runner) == "missing"
        assert srv._win_service_exists("X", runner=runner) is False

    def test_andere_fehler_heissen_unbekannt_nicht_fehlt(self, srv):
        """Log-Audit A9 (LC-6): waehrend des Herunterfahrens meldet sc z. B.
        1115 — frueher galt jeder Fehler als "Dienst fehlt", der Wachhund rief
        pg_ctl register auf und beendete sich mit Exit 1."""
        runner = lambda argv, **kw: _result(1115, "FEHLER 1115")  # noqa: E731
        assert srv._win_service_state("X", runner=runner) == "unknown"
        assert srv._win_service_exists("X", runner=runner) is True

    def test_sc_nicht_startbar_heisst_unbekannt(self, srv):
        def runner(argv, **kw):
            raise OSError("sc fehlt")

        assert srv._win_service_state("X", runner=runner) == "unknown"

    def test_deutsche_ausgabe_wird_gelesen(self, srv):
        runner = lambda argv, **kw: _result(0, _SC_DE_STOP_PENDING)  # noqa: E731
        assert srv._win_service_state("X", runner=runner) == "STOP_PENDING"

    def test_englische_ausgabe_wird_gelesen(self, srv):
        runner = lambda argv, **kw: _result(0, _SC_EN_RUNNING)  # noqa: E731
        assert srv._win_service_state("X", runner=runner) == "RUNNING"

    def test_ausgabe_ohne_zustand_ist_unbekannt_aber_vorhanden(self, srv):
        runner = lambda argv, **kw: _result(0, "")  # noqa: E731
        assert srv._win_service_state("X", runner=runner) == "unknown"
        assert srv._win_service_exists("X", runner=runner) is True


class TestPgIsreadyAblehnend:
    """pg_isready Exit 1 = Server lehnt ab (faehrt hoch oder herunter) — das ist
    kein "down", der Wachhund darf deshalb nicht neu starten (Log-Audit A9)."""

    @pytest.fixture(autouse=True)
    def _unix(self, srv, tmp_path, monkeypatch):
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        monkeypatch.setattr(srv, "DATA_DIR", tmp_path)

    def test_rc1_ist_unbekannt(self, srv, monkeypatch):
        monkeypatch.setattr(srv.subprocess, "run", lambda argv, **kw: _result(1))
        assert srv.pg_cluster_state() == "unknown"

    def test_rc2_ist_down(self, srv, monkeypatch):
        monkeypatch.setattr(srv.subprocess, "run", lambda argv, **kw: _result(2))
        assert srv.pg_cluster_state() == "down"


# --- A9: Wachhund ---------------------------------------------------------------

class TestPgWachhundBeimHerunterfahren:
    """Log-Audit A9 (LC-5/LC-6/PG-2/BO-6): Beim Herunterfahren stoppt Windows den
    PostgreSQL-Dienst parallel zu PraxisZeit. Der Wachhund sah "down" und
    startete PostgreSQL sofort neu (3 Mal tatsaechlich), zweimal lief er dabei in
    "pg_ctl register" und beendete sich mit Exit 1."""

    def _setup(self, srv, monkeypatch, states, *, windows=True, service="RUNNING",
               shutting_down=False):
        seq = iter(states)
        monkeypatch.setattr(srv, "IS_WINDOWS", windows)
        monkeypatch.setattr(srv, "load_config", lambda: {})
        monkeypatch.setattr(srv, "pg_cluster_state", lambda: next(seq))
        called = []
        svc = iter(service) if isinstance(service, list) else None
        monkeypatch.setattr(
            srv, "_win_service_state",
            lambda name, **kw: (next(svc) if svc else service),
        )
        monkeypatch.setattr(srv, "_win_system_shutting_down", lambda: shutting_down)
        monkeypatch.setattr(srv, "pg_start", lambda: called.append("pg_start"))
        monkeypatch.setattr(srv, "_win_pg_register_and_start",
                            lambda: called.append("register"))
        monkeypatch.setattr(srv, "uvicorn_stop", lambda: called.append("uvicorn_stop"))
        monkeypatch.setattr(srv, "_remove_pid", lambda: called.append("_remove_pid"))
        return called

    def test_einmal_down_startet_nicht_neu(self, srv, monkeypatch):
        called = self._setup(srv, monkeypatch, ["down"] * (srv.WATCHDOG_PG_DOWN_LIMIT - 1))
        for _ in range(srv.WATCHDOG_PG_DOWN_LIMIT - 1):
            srv._watchdog_check_pg(is_stopping=lambda: False)
        assert called == []

    def test_mehrmals_down_in_folge_startet_neu(self, srv, monkeypatch):
        n = srv.WATCHDOG_PG_DOWN_LIMIT
        assert 2 <= n <= 3
        called = self._setup(srv, monkeypatch, ["down"] * n)
        for _ in range(n):
            srv._watchdog_check_pg(is_stopping=lambda: False)
        assert called == ["pg_start"]

    def test_eigene_antwort_dazwischen_setzt_den_zaehler_zurueck(self, srv, monkeypatch):
        n = srv.WATCHDOG_PG_DOWN_LIMIT
        states = ["down"] * (n - 1) + ["own"] + ["down"] * (n - 1)
        called = self._setup(srv, monkeypatch, states)
        for _ in states:
            srv._watchdog_check_pg(is_stopping=lambda: False)
        assert called == []

    def test_stop_pending_startet_nicht_neu(self, srv, monkeypatch):
        n = srv.WATCHDOG_PG_DOWN_LIMIT
        called = self._setup(srv, monkeypatch, ["down"] * n, service="STOP_PENDING")
        for _ in range(n):
            srv._watchdog_check_pg(is_stopping=lambda: False)
        assert called == []

    def test_nach_stop_pending_folgt_neustart_wenn_der_dienst_steht(self, srv, monkeypatch):
        """Manuelles ``net stop`` durch die Verwaltung: erst STOP_PENDING, dann
        STOPPED — ohne Herunterfahren startet der Wachhund wie bisher neu."""
        n = srv.WATCHDOG_PG_DOWN_LIMIT
        called = self._setup(srv, monkeypatch, ["down"] * (n + 1),
                             service=["STOP_PENDING", "STOPPED"])
        for _ in range(n + 1):
            srv._watchdog_check_pg(is_stopping=lambda: False)
        assert called == ["pg_start"]

    def test_windows_faehrt_herunter(self, srv, monkeypatch):
        n = srv.WATCHDOG_PG_DOWN_LIMIT
        called = self._setup(srv, monkeypatch, ["down"] * n, shutting_down=True)
        for _ in range(n):
            srv._watchdog_check_pg(is_stopping=lambda: False)
        assert called == []

    def test_unbekannter_dienstzustand_startet_nicht_und_registriert_nie(self, srv, monkeypatch):
        n = srv.WATCHDOG_PG_DOWN_LIMIT
        called = self._setup(srv, monkeypatch, ["down"] * n, service="unknown")
        for _ in range(n):
            srv._watchdog_check_pg(is_stopping=lambda: False)
        assert called == []

    def test_fehlender_dienst_wird_nicht_aus_dem_wachhund_registriert(self, srv, monkeypatch):
        """Registrieren gehoert allein zum Dienststart: der Manager beendet sich
        mit 1, NSSM startet ihn neu, und cmd_start registriert den Dienst."""
        n = srv.WATCHDOG_PG_DOWN_LIMIT
        called = self._setup(srv, monkeypatch, ["down"] * n, service="missing")
        for _ in range(n - 1):
            srv._watchdog_check_pg(is_stopping=lambda: False)
        with pytest.raises(SystemExit) as e:
            srv._watchdog_check_pg(is_stopping=lambda: False)
        assert e.value.code == 1
        assert "register" not in called and "pg_start" not in called
        assert called == ["uvicorn_stop", "_remove_pid"]

    def test_stoppwunsch_direkt_vor_dem_start(self, srv, monkeypatch):
        """Der Stoppwunsch wird NACH der Dienstabfrage noch einmal gelesen."""
        n = srv.WATCHDOG_PG_DOWN_LIMIT
        called = self._setup(srv, monkeypatch, ["down"] * n)
        stopp = {"jetzt": False}

        def dienst(name, **kw):
            stopp["jetzt"] = True  # Ctrl+C kommt waehrend der sc-Abfrage
            return "STOPPED"

        monkeypatch.setattr(srv, "_win_service_state", dienst)
        for _ in range(n):
            srv._watchdog_check_pg(is_stopping=lambda: stopp["jetzt"])
        assert called == []

    def test_unix_braucht_keine_dienstabfrage(self, srv, monkeypatch):
        n = srv.WATCHDOG_PG_DOWN_LIMIT
        called = self._setup(srv, monkeypatch, ["down"] * n, windows=False)

        def nie(name, **kw):
            raise AssertionError("sc darf unter Unix nicht laufen")

        monkeypatch.setattr(srv, "_win_service_state", nie)
        for _ in range(n):
            srv._watchdog_check_pg(is_stopping=lambda: False)
        assert called == ["pg_start"]


# --- A6: Startdiagnose PostgreSQL unter Windows ------------------------------

class TestPgStartdiagnose:
    def test_net_start_fehler_wird_protokolliert(self, srv, caplog):
        runner = lambda argv, **kw: _result(2, "", "Systemfehler 1069 ist aufgetreten.")  # noqa: E731
        with caplog.at_level(logging.WARNING, logger="praxiszeit"):
            rc = srv._win_net_start("PraxisZeit-PostgreSQL", runner=runner)
        assert rc == 2
        assert "1069" in caplog.text and "rc=2" in caplog.text

    def test_bereits_gestartet_2182_ist_still(self, srv, caplog):
        runner = lambda argv, **kw: _result(  # noqa: E731
            2, "Der angeforderte Dienst wurde bereits gestartet.\r\n"
               "Sie erhalten weitere Hilfe, wenn Sie NET HELPMSG 2182 eingeben.")
        with caplog.at_level(logging.WARNING, logger="praxiszeit"):
            srv._win_net_start("PraxisZeit-PostgreSQL", runner=runner)
        assert caplog.text == ""

    def test_net_start_argv_bleibt_gleich(self, srv):
        calls = []
        srv._win_net_start("PraxisZeit-PostgreSQL",
                           runner=lambda argv, **kw: calls.append(argv) or _result(0))
        assert calls == [["net", "start", "PraxisZeit-PostgreSQL"]]

    def test_veraltete_logdatei_wird_nicht_ausgegeben(self, srv, tmp_path, monkeypatch, caplog):
        """Kundenfall 26.05.: ausgegeben wurde viermal das postgresql-startup.log
        vom 03.05.; der VC++-Hinweis fiel dadurch weg."""
        monkeypatch.setattr(srv, "LOG_DIR", tmp_path)
        alt = tmp_path / "postgresql-startup.log"
        alt.write_text("2026-05-03 alte Zeilen\n", encoding="utf-8")
        old = time.time() - 30 * 86400
        os.utime(alt, (old, old))
        with caplog.at_level(logging.ERROR, logger="praxiszeit"):
            assert srv._dump_pg_startup_log(since=time.time() - 5) is False
        assert "alte Zeilen" not in caplog.text

    def test_frische_logdatei_wird_ausgegeben(self, srv, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr(srv, "LOG_DIR", tmp_path)
        start = time.time() - 5
        (tmp_path / "postgresql.log").write_text("FATAL: could not open log file\n",
                                                 encoding="utf-8")
        with caplog.at_level(logging.ERROR, logger="praxiszeit"):
            assert srv._dump_pg_startup_log(since=start) is True
        assert "could not open log file" in caplog.text

    def test_ohne_zeitgrenze_wie_bisher(self, srv, tmp_path, monkeypatch):
        monkeypatch.setattr(srv, "LOG_DIR", tmp_path)
        (tmp_path / "postgresql.log").write_text("x\n", encoding="utf-8")
        assert srv._dump_pg_startup_log() is True

    def test_veraltetes_startup_log_wird_einmal_umbenannt(self, srv, tmp_path, monkeypatch):
        monkeypatch.setattr(srv, "LOG_DIR", tmp_path)
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        (tmp_path / "postgresql-startup.log").write_text("alt\n", encoding="utf-8")
        assert srv._retire_stale_startup_log() is True
        assert not (tmp_path / "postgresql-startup.log").exists()
        assert (tmp_path / "postgresql-startup.log.old").read_text(encoding="utf-8") == "alt\n"
        assert srv._retire_stale_startup_log() is False

    def test_unix_behaelt_das_startup_log(self, srv, tmp_path, monkeypatch):
        """Unter Unix schreibt ``pg_ctl start -l`` genau diese Datei."""
        monkeypatch.setattr(srv, "LOG_DIR", tmp_path)
        monkeypatch.setattr(srv, "IS_WINDOWS", False)
        (tmp_path / "postgresql-startup.log").write_text("x\n", encoding="utf-8")
        assert srv._retire_stale_startup_log() is False
        assert (tmp_path / "postgresql-startup.log").exists()

    def test_eventlog_abfrage(self, srv, caplog):
        calls = []

        def runner(argv, **kw):
            calls.append(argv)
            return _result(0, "Event[0]:\n  Source: PostgreSQL\n  Description: FATAL: xyz\n")

        with caplog.at_level(logging.ERROR, logger="praxiszeit"):
            assert srv._dump_win_pg_eventlog(runner=runner) is True
        assert calls[0][:3] == ["wevtutil", "qe", "Application"]
        assert any("Provider[@Name='PostgreSQL']" in a for a in calls[0])
        assert "FATAL: xyz" in caplog.text

    def test_eventlog_leer_oder_fehler(self, srv):
        assert srv._dump_win_pg_eventlog(runner=lambda argv, **kw: _result(0, "")) is False

        def kaputt(argv, **kw):
            raise OSError("wevtutil fehlt")

        assert srv._dump_win_pg_eventlog(runner=kaputt) is False

    def test_zeitgrenze_protokolliert_dienstzustand_und_eventlog(
        self, srv, tmp_path, monkeypatch, caplog
    ):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "postgresql-startup.log").write_text("alt\n", encoding="utf-8")
        monkeypatch.setattr(srv, "IS_WINDOWS", True)
        monkeypatch.setattr(srv, "LOG_DIR", log_dir)
        monkeypatch.setattr(srv, "PG_DATA", tmp_path / "db")
        monkeypatch.setattr(srv, "load_config", lambda: {})
        monkeypatch.setattr(srv, "_win_grant_networkservice", lambda *a, **kw: None)
        monkeypatch.setattr(srv, "pg_cluster_state", lambda: "down")
        clock = {"t": 1000.0}
        monkeypatch.setattr(srv.time, "monotonic", lambda: clock["t"])
        monkeypatch.setattr(srv.time, "sleep",
                            lambda s: clock.__setitem__("t", clock["t"] + max(s, 1)))
        calls = []

        def run(argv, *a, **kw):
            argv = [str(x) for x in argv]
            calls.append(argv)
            if argv[:2] == ["sc", "query"]:
                return _result(0, _SC_EN_RUNNING)
            if argv[:2] == ["sc", "queryex"]:
                return _result(0, "STATE : 1  STOPPED\nWIN32_EXIT_CODE : 1067")
            return _result(0, "")

        monkeypatch.setattr(srv.subprocess, "run", run)
        with caplog.at_level(logging.ERROR, logger="praxiszeit"), \
                pytest.raises(SystemExit) as e:
            srv.pg_start()
        assert e.value.code == 1
        assert ["sc", "queryex", "PraxisZeit-PostgreSQL"] in calls
        assert any(c[:2] == ["wevtutil", "qe"] for c in calls)
        assert "WIN32_EXIT_CODE : 1067" in caplog.text
        # Die alte Datei ist zur Seite gelegt und unterdrueckt den Hinweis nicht.
        assert "postgresql-startup.log" not in caplog.text
        assert not (log_dir / "postgresql-startup.log").exists()
        assert "Visual C++" in caplog.text


# --- A8: Uhrzeit in den uvicorn-Meldungen ------------------------------------

class TestUvicornLogKonfiguration:
    def test_formate_tragen_die_uhrzeit(self, srv):
        cfg = srv.uvicorn_log_config()
        for name in ("default", "access"):
            assert "%(asctime)s" in cfg["formatters"][name]["fmt"]
            assert cfg["formatters"][name]["use_colors"] is False

    def test_zugriffsprotokoll_bleibt(self, srv):
        cfg = srv.uvicorn_log_config()
        access = cfg["loggers"]["uvicorn.access"]
        assert access["handlers"] == ["access"]
        assert access["level"] == "INFO"
        assert cfg["handlers"]["access"]["stream"] == "ext://sys.stdout"

    def test_app_meldungen_bekommen_einen_handler(self, srv):
        """``praxiszeit.security`` (AUTH login_failed) hatte keinen Handler und
        lief ueber Pythons lastResort — ohne Uhrzeit. Die Wurzel bekommt jetzt
        einen Handler mit Uhrzeit, auf WARNING wie lastResort."""
        cfg = srv.uvicorn_log_config()
        assert cfg["root"]["handlers"] == ["default"]
        assert cfg["root"]["level"] == "WARNING"
        assert cfg["disable_existing_loggers"] is False

    def test_security_logger_reicht_nicht_an_die_wurzel_weiter(self, srv):
        # Ausgabe allein ueber den Handler aus app/core/log_setup.py (mit ip=).
        sec = srv.uvicorn_log_config()["loggers"]["praxiszeit.security"]
        assert sec["propagate"] is False
        assert sec["level"] == "INFO"
        assert "handlers" not in sec

    def _apply_like_production(self, srv, capsys):
        """Reihenfolge wie im Dienst: uvicorn wendet ``--log-config`` an, danach
        importiert er die App, und ``app.main`` haengt den eigenen Handler an
        ``praxiszeit.security`` (backend/app/core/log_setup.py)."""
        pytest.importorskip("uvicorn")
        log_setup = pytest.importorskip("app.core.log_setup")
        names = ("uvicorn", "uvicorn.error", "uvicorn.access", "praxiszeit.security")
        saved = {n: (logging.getLogger(n).handlers[:], logging.getLogger(n).propagate,
                     logging.getLogger(n).level) for n in names}
        root = logging.getLogger()
        saved_root = (root.handlers[:], root.level)
        logging.config.dictConfig(json.loads(json.dumps(srv.uvicorn_log_config())))
        log_setup.install_security_log_handler()

        def restore():
            root.handlers, root.level = saved_root[0], saved_root[1]
            for n, (handlers, propagate, level) in saved.items():
                lg = logging.getLogger(n)
                lg.handlers, lg.propagate, lg.level = handlers, propagate, level
        return restore

    def test_konfiguration_laesst_sich_anwenden(self, srv, capsys):
        restore = self._apply_like_production(srv, capsys)
        try:
            logging.getLogger("praxiszeit.security").warning("AUTH login_failed user=x")
            logging.getLogger("app.irgendwas").warning("WARNUNG aus der App")
            err = capsys.readouterr().err
        finally:
            restore()
        import re
        assert re.search(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", err), err
        assert "praxiszeit.security" in err and "AUTH login_failed" in err
        assert "WARNUNG aus der App" in err

    def test_auth_zeilen_erscheinen_genau_einmal(self, srv, capsys):
        """Review-Fund zum Log-Audit A8 (Kundenfall 2026-11-15): mit dem
        Wurzel-Handler lief jede AUTH-Zeile doppelt in service-stderr.log (einmal
        mit ``ip=``, einmal ohne), INFO-Zeilen ebenso — der weitergereichte
        Datensatz pruefte die WARNING-Stufe der Wurzel nicht. Zaehlen
        fehlgeschlagener Anmeldungen waere so unzuverlaessig."""
        restore = self._apply_like_production(srv, capsys)
        try:
            sec = logging.getLogger("praxiszeit.security")
            sec.info("AUTH login_success user=a")
            sec.warning("AUTH login_failed user=b")
            err = capsys.readouterr().err
        finally:
            restore()
        lines = [ln for ln in err.splitlines() if "AUTH " in ln]
        assert len(lines) == 2, err
        assert all("ip=" in ln for ln in lines), err

    def test_datei_wird_geschrieben(self, srv, tmp_path):
        path = srv.write_uvicorn_log_config(tmp_path / "uvicorn-log.json")
        assert path == tmp_path / "uvicorn-log.json"
        assert json.loads(path.read_text(encoding="utf-8")) == srv.uvicorn_log_config()

    def test_schreibfehler_startet_ohne_log_config(self, srv, tmp_path):
        ziel = tmp_path / "datei"
        ziel.write_text("x")
        # Elternpfad ist eine Datei -> nicht schreibbar
        assert srv.write_uvicorn_log_config(ziel / "uvicorn-log.json") is None


# --- uvicorn_start: Protokoll der Gesundheitspruefung + --log-config ---------

class _FakePopen:
    last = None

    def __init__(self, cmd, **kw):
        _FakePopen.last = cmd
        self.returncode = None

    def poll(self):
        return None


class TestUvicornStart:
    def _run(self, srv, tmp_path, monkeypatch, config):
        urls = []
        monkeypatch.setattr(srv, "DATA_DIR", tmp_path)
        monkeypatch.setattr(srv, "port_is_occupied", lambda h, p: False)
        monkeypatch.setattr(srv, "_ensure_self_signed_cert", lambda *a, **kw: False)
        monkeypatch.setattr(srv.subprocess, "Popen", _FakePopen)

        def healthy(process, probe, **kw):
            probe()
            return True

        monkeypatch.setattr(srv, "wait_until_healthy", healthy)
        import urllib.request

        def urlopen(req, **kw):
            urls.append(req.full_url)
            raise OSError("nicht bereit")

        monkeypatch.setattr(urllib.request, "urlopen", urlopen)
        srv.uvicorn_start(config)
        return _FakePopen.last, urls

    def test_f054_fehlendes_zertifikat_prueft_per_http(self, srv, tmp_path, monkeypatch):
        """F-054 (1.3.4) Regressionstest: ssl_cert konfiguriert, Datei fehlt ->
        uvicorn laeuft ohne TLS, also muss auch die Pruefung http sprechen. Sonst
        4 Tage Neustartschleife (Kundenfall, 166.000 "Invalid HTTP request")."""
        config = {"server": {"port": 18443, "bind_address": "127.0.0.1",
                             "ssl_cert": str(tmp_path / "fehlt.pem"),
                             "ssl_key": str(tmp_path / "fehlt-key.pem")}}
        cmd, urls = self._run(srv, tmp_path, monkeypatch, config)
        assert "--ssl-certfile" not in cmd
        assert urls == ["http://localhost:18443/api/health"]

    def test_f054_vorhandenes_zertifikat_prueft_per_https(self, srv, tmp_path, monkeypatch):
        cert = tmp_path / "cert.pem"
        key = tmp_path / "key.pem"
        cert.write_text("c")
        key.write_text("k")
        config = {"server": {"port": 18443, "bind_address": "127.0.0.1",
                             "ssl_cert": str(cert), "ssl_key": str(key)}}
        cmd, urls = self._run(srv, tmp_path, monkeypatch, config)
        assert "--ssl-certfile" in cmd
        assert urls == ["https://localhost:18443/api/health"]

    def test_log_config_wird_uebergeben(self, srv, tmp_path, monkeypatch):
        config = {"server": {"port": 18080, "bind_address": "127.0.0.1"}}
        cmd, _ = self._run(srv, tmp_path, monkeypatch, config)
        i = cmd.index("--log-config")
        assert Path(cmd[i + 1]) == tmp_path / "uvicorn-log.json"
        assert (tmp_path / "uvicorn-log.json").is_file()


# --- D/NET-8: [server] allowed_hosts -----------------------------------------

class TestAllowedHosts:
    # Review-Fund (Kundenfall 2026-11-15): die eigene Gesundheitspruefung des
    # Managers und der Update-Assistent fragen http(s)://localhost:<port>. Fehlt
    # localhost in der Liste, antwortet TrustedHost mit 400, der Start gilt als
    # gescheitert und NSSM startet den Dienst in einer Schleife neu.
    _LOCAL = ",localhost,127.0.0.1"

    def test_zeichenkette(self, srv):
        env = {}
        srv.apply_config_env({"server": {"allowed_hosts": "praxis.local,192.168.1.10"}}, env)
        assert env["ALLOWED_HOSTS"] == "praxis.local,192.168.1.10" + self._LOCAL

    def test_liste(self, srv):
        env = {}
        srv.apply_config_env({"server": {"allowed_hosts": ["praxis.local", "192.168.1.10"]}}, env)
        assert env["ALLOWED_HOSTS"] == "praxis.local,192.168.1.10" + self._LOCAL

    def test_localhost_wird_immer_ergaenzt(self, srv):
        env = {}
        srv.apply_config_env({"server": {"allowed_hosts": "praxis-pc"}}, env)
        assert env["ALLOWED_HOSTS"].split(",") == ["praxis-pc", "localhost", "127.0.0.1"]

    def test_keine_doppelten_eintraege(self, srv):
        env = {}
        # TrustedHost vergleicht exakt; der Probe-Host ist klein geschrieben.
        srv.apply_config_env({"server": {"allowed_hosts": "localhost, praxis-pc"}}, env)
        assert env["ALLOWED_HOSTS"].split(",") == ["localhost", "praxis-pc", "127.0.0.1"]

    def test_stern_bleibt_unveraendert(self, srv):
        env = {}
        srv.apply_config_env({"server": {"allowed_hosts": "*"}}, env)
        assert env["ALLOWED_HOSTS"] == "*"

    def test_ohne_eintrag_kein_wert(self, srv):
        env = {}
        srv.apply_config_env({}, env)
        assert "ALLOWED_HOSTS" not in env

    def test_wert_aus_der_umgebung_bekommt_localhost(self, srv):
        env = {"ALLOWED_HOSTS": "praxis-pc"}
        srv.apply_config_env({"server": {"allowed_hosts": "anders"}}, env)
        assert env["ALLOWED_HOSTS"] == "praxis-pc" + self._LOCAL

    def test_gesundheitspruefung_besteht_trustedhost(self, srv):
        """Ende-zu-Ende gegen dieselbe Middleware wie backend/app/main.py."""
        pytest.importorskip("starlette")
        from starlette.applications import Starlette
        from starlette.middleware.trustedhost import TrustedHostMiddleware
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route
        from starlette.testclient import TestClient

        env = {}
        srv.apply_config_env({"server": {"allowed_hosts": "praxis-pc,192.168.1.10"}}, env)
        hosts = [h.strip() for h in env["ALLOWED_HOSTS"].split(",") if h.strip()]
        app = Starlette(routes=[Route("/api/health", lambda r: PlainTextResponse("ok"))])
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
        client = TestClient(app)
        for host in ("localhost:8080", "127.0.0.1:8080", "praxis-pc"):
            assert client.get("/api/health", headers={"host": host}).status_code == 200, host
        assert client.get("/api/health", headers={"host": "boese.example"}).status_code == 400
