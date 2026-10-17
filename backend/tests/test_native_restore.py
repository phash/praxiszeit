"""Nativer Restore (Linux/macOS): ``praxiszeit-server.py restore <datei>``
(Gesamtreview 1.20).

Bis 1.20 beschrieb ``docs/BACKUP.md`` fuer Linux/macOS nur: Dump bei
LAUFENDEM Dienst durch das gebuendelte ``psql`` leiten — ohne
``ON_ERROR_STOP``, ohne frische Datenbank, ohne Neustart. Nativ laufen die
Migrationen aber nur in ``cmd_start``/``cmd_init``. Ein Backup einer aelteren
Version (Serverumzug auf eine frische 1.20-Installation, Rollback-Vorbereitung)
setzte ``alembic_version`` zurueck, der laufende 1.20-Prozess arbeitete gegen
das alte Schema (072: ``users.work_blocks`` fehlt → Login HTTP 500 bis zum
naechsten Dienststart). Ein Backup von 070 oder aelter brach am Fremdschluessel
von ``security_events`` auf ``users_pkey`` ab, und ohne ``ON_ERROR_STOP`` lief
``psql`` weiter und hinterliess mit Exit 0 eine halb eingespielte Datenbank.
Windows machte es mit ``restore-backup.bat`` schon richtig (Dienst anhalten,
frische Datenbank, einspielen, Dienst starten).

``restore`` spielt das Backup zuerst in eine Zwischendatenbank ein und ersetzt
die bisherige erst, wenn das Einspielen gelungen ist und das Backup von einer
Version stammt, die diese Installation kennt. Migriert wird beim naechsten
Dienststart — wie unter Docker (``restore.sh``) und wie beim Rollback noetig
(Backup mit der installierten Version einspielen, dann die alte Version
installieren: deren Start findet den Stand des Backups vor).

Die Tests ersetzen ``psql`` durch eine Attrappe, die die Datenbanken des
Clusters als Woerterbuch fuehrt. Wie ``test_native_pg_lifecycle.py`` brauchen
sie ``praxiszeit-server.py`` im Repo-Wurzelverzeichnis.
"""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import logging
import os
import re
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SERVER_PATH = _REPO / "praxiszeit-server.py"

pytestmark = pytest.mark.skipif(
    not _SERVER_PATH.exists(),
    reason=f"praxiszeit-server.py nicht erreichbar unter {_SERVER_PATH} (Backend-Container ohne Repo)",
)

_DUMP = (
    "--\n-- PostgreSQL database dump\n--\n\\restrict abc\n"
    "CREATE TABLE users ();\n"
    "--\n-- PostgreSQL database dump complete\n--\n\n\\unrestrict abc\n\n"
)
_OLD = "BESTAND"


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("praxiszeit_server_restore", _SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeCluster:
    """``psql`` der gebuendelten Installation: Datenbanken als Woerterbuch."""

    def __init__(self, *, revision="072_cr_sunday_reason", fail_load=False,
                 fail_rename=False, interrupt_rename=False, has_alembic=True):
        self.dbs = {"postgres": "", "praxiszeit": _OLD}
        self.revision = revision
        self.fail_load = fail_load
        self.fail_rename = fail_rename
        self.interrupt_rename = interrupt_rename
        self.has_alembic = has_alembic
        self.calls: list[list[str]] = []
        self.events: list[str] = []
        self.envs: list[dict] = []
        self.load_mode = None

    def __call__(self, cmd, **kw):
        if Path(cmd[0]).name != "psql":
            raise AssertionError(f"unerwarteter Aufruf: {cmd}")
        self.calls.append(list(cmd))
        self.envs.append(kw.get("env") or {})
        db = cmd[cmd.index("-d") + 1]
        if db not in self.dbs:
            return subprocess.CompletedProcess(cmd, 2, "", f'FATAL: database "{db}" does not exist')
        out = []
        if "-f" in cmd:
            path = Path(cmd[cmd.index("-f") + 1])
            if path.name == "init-db-user.sql":
                self.events.append(f"grants:{db}")
                return subprocess.CompletedProcess(cmd, 0, "", "")
            self.load_mode = path.stat().st_mode & 0o777
            self.events.append(f"load:{db}")
            if self.fail_load:
                self.dbs[db] = "TEIL"
                return subprocess.CompletedProcess(
                    cmd, 3, "", 'psql:/x.sql:17: ERROR:  relation "users" already exists\n')
            self.dbs[db] = path.read_text(encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        for i, arg in enumerate(cmd):
            if arg != "-c":
                continue
            sql = cmd[i + 1]
            names = re.findall(r'"([^"]+)"', sql)
            if sql.startswith("DROP DATABASE"):
                self.events.append(f"drop:{names[0]}")
                self.dbs.pop(names[0], None)
            elif sql.startswith("CREATE DATABASE"):
                self.events.append(f"create:{names[0]}")
                self.dbs[names[0]] = ""
            elif sql.startswith("ALTER DATABASE"):
                self.events.append(f"rename:{names[0]}->{names[1]}")
                if self.interrupt_rename:
                    raise KeyboardInterrupt
                if self.fail_rename:
                    return subprocess.CompletedProcess(cmd, 1, "", "ERROR:  rename failed\n")
                self.dbs[names[1]] = self.dbs.pop(names[0])
            elif "alembic_version" in sql:
                self.events.append(f"revision:{db}")
                if not self.has_alembic:
                    return subprocess.CompletedProcess(
                        cmd, 1, "", 'ERROR:  relation "alembic_version" does not exist\n')
                out.append(f"{self.revision}\n")
            elif "pg_database" in sql:
                name = re.search(r"datname = '([^']+)'", sql).group(1)
                out.append("1\n" if name in self.dbs else "")
            else:
                raise AssertionError(f"unerwartetes SQL: {sql}")
        return subprocess.CompletedProcess(cmd, 0, "".join(out), "")


@pytest.fixture
def inst(srv, tmp_path, monkeypatch):
    """Installationsordner mit data/, config/ und app/backend/alembic/versions."""
    data = tmp_path / "data"
    (data / "backups").mkdir(parents=True)
    backend = tmp_path / "app" / "backend"
    versions = backend / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "__init__.py").write_text("", encoding="utf-8")
    (versions / "x_072.py").write_text('revision = "072_cr_sunday_reason"\n', encoding="utf-8")
    (versions / "x_073.py").write_text(
        'revision = "073_work_blocks"\ndown_revision = "072_cr_sunday_reason"\n', encoding="utf-8")
    (backend / "init-db-user.sql").write_text("GRANT CONNECT ON DATABASE praxiszeit TO x;\n",
                                              encoding="utf-8")
    monkeypatch.setattr(srv, "DATA_DIR", data)
    monkeypatch.setattr(srv, "PID_FILE", data / "praxiszeit.pid")
    monkeypatch.setattr(srv, "BACKEND_DIR", backend)
    monkeypatch.setattr(srv, "IS_WINDOWS", False)
    monkeypatch.setattr(srv, "IS_MACOS", False)
    monkeypatch.setattr(srv, "load_config", lambda: {})
    monkeypatch.setattr(srv, "pg_load_credentials", lambda: ("su-pw", "app-pw"))
    monkeypatch.setattr(srv, "_running_as_root", lambda: False)
    monkeypatch.setattr(srv, "_install_owner", lambda: "dienstkonto")
    monkeypatch.setattr(srv, "bundled_python", lambda: "/inst/bin/python/bin/python3")
    return tmp_path


def _dump(inst: Path, text: str = _DUMP, name: str = "praxiszeit_20261017_120000.sql.gz") -> Path:
    path = inst / "data" / "backups" / name
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _restore(srv, file: Path, cluster: FakeCluster, *, pg_running=True, caplog=None):
    state = {"running": pg_running, "started": 0, "stopped": 0}

    def _start():
        state["started"] += 1
        state["running"] = True

    def _stop():
        state["stopped"] += 1
        state["running"] = False

    code = 0
    with patch.object(srv, "pg_is_running", side_effect=lambda: state["running"]), \
         patch.object(srv, "pg_start", side_effect=_start), \
         patch.object(srv, "pg_stop", side_effect=_stop), \
         patch.object(srv.subprocess, "run", side_effect=cluster):
        try:
            srv.cmd_restore(argparse.Namespace(file=str(file)))
        except SystemExit as exc:
            code = exc.code
    return code, state


# --- Ablauf -------------------------------------------------------------------

def test_restore_ersetzt_die_datenbank_durch_das_backup(srv, inst):
    cluster = FakeCluster()
    code, _ = _restore(srv, _dump(inst), cluster)
    assert code == 0
    assert cluster.dbs == {"postgres": "", "praxiszeit": _DUMP}


def test_restore_spielt_erst_in_eine_zwischendatenbank_ein(srv, inst):
    cluster = FakeCluster()
    _restore(srv, _dump(inst), cluster)
    assert cluster.events == [
        "drop:praxiszeit_restore",
        "create:praxiszeit_restore",
        "load:praxiszeit_restore",
        "revision:praxiszeit_restore",
        "drop:praxiszeit",
        "rename:praxiszeit_restore->praxiszeit",
        "grants:praxiszeit",
    ]


def test_einspielen_bricht_beim_ersten_fehler_ab(srv, inst):
    cluster = FakeCluster()
    _restore(srv, _dump(inst), cluster)
    load = next(c for c in cluster.calls if "-f" in c and not c[-1].endswith("init-db-user.sql"))
    assert "ON_ERROR_STOP=1" in load
    # Kein ~/.psqlrc des Aufrufers, keine Passwortabfrage.
    assert "-X" in load and "-w" in load
    # Das Passwort steht in der Umgebung, nie in der Befehlszeile (Prozessliste).
    assert all("su-pw" not in arg for c in cluster.calls for arg in c)
    assert all(env.get("PGPASSWORD") == "su-pw" for env in cluster.envs)


def test_rechte_wie_bei_der_erstinitialisierung(srv, inst):
    cluster = FakeCluster()
    _restore(srv, _dump(inst), cluster)
    grants = [c for c in cluster.calls if c[-1].endswith("init-db-user.sql")]
    assert len(grants) == 1
    assert grants[0][grants[0].index("-d") + 1] == "praxiszeit"
    assert "ON_ERROR_STOP=1" in grants[0]


def test_entpackter_dump_ist_privat_und_wird_entfernt(srv, inst):
    cluster = FakeCluster()
    _restore(srv, _dump(inst), cluster)
    assert cluster.load_mode == 0o600
    assert not list((inst / "data").glob("*.sql")), list((inst / "data").iterdir())
    assert not list((inst / "data").glob(".restore-*")), list((inst / "data").iterdir())


def test_relativer_pfad_gilt_ab_dem_aufrufverzeichnis(srv, inst, monkeypatch):
    dump = _dump(inst)
    monkeypatch.chdir(dump.parent)
    cluster = FakeCluster()
    code, _ = _restore(srv, Path(dump.name), cluster)
    assert code == 0
    assert cluster.dbs["praxiszeit"] == _DUMP


def test_meldet_dienststart_und_migration(srv, inst, caplog):
    with caplog.at_level(logging.INFO, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst), FakeCluster())
    assert code == 0
    assert "systemctl start praxiszeit" in caplog.text
    assert "Migration" in caplog.text
    assert "072_cr_sunday_reason" in caplog.text


def test_aelteres_backup_nennt_den_rollback_weg(srv, inst, caplog):
    """Gesamtreview 1.20, Runde 2: der Installer ersetzt ``app/`` nicht, er
    kopiert nur darueber. Nach ``restore`` + altem Paket lag die Migration der
    neueren Version weiter in ``alembic/versions``; der Start der alten Version
    wandte sie erneut an (073: ``users.scheduled_*`` weg, 1.19.3 startet nicht mehr).
    Wer ``restore`` fuer einen Rollback nutzt, liest an dieser Stelle „Jetzt
    den Dienst starten" — die Meldung muss den Rollback-Weg nennen."""
    with caplog.at_level(logging.INFO, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst), FakeCluster(revision="072_cr_sunday_reason"))
    assert code == 0
    app = inst / "app"
    assert "Rollback" in caplog.text
    assert f"sudo mv {app} {app}.neu" in caplog.text
    assert "NICHT starten" in caplog.text


def test_backup_dieser_version_nennt_keinen_rollback(srv, inst, caplog):
    with caplog.at_level(logging.INFO, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst), FakeCluster(revision="073_work_blocks"))
    assert code == 0
    assert "systemctl start praxiszeit" in caplog.text
    assert "Rollback" not in caplog.text


def test_migration_heads_folgen_der_kette(srv, tmp_path):
    (tmp_path / "a.py").write_text("revision = '001'\ndown_revision = None\n", encoding="utf-8")
    (tmp_path / "b.py").write_text(
        "revision: str = '002'\ndown_revision: Union[str, None] = '001'\n", encoding="utf-8")
    (tmp_path / "c.py").write_text('revision = "003a"\ndown_revision = "002"\n', encoding="utf-8")
    (tmp_path / "d.py").write_text('revision = "003b"\ndown_revision = "002"\n', encoding="utf-8")
    (tmp_path / "e.py").write_text(
        'revision = "004"\ndown_revision = ("003a", "003b")\n', encoding="utf-8")
    assert srv.migration_heads(tmp_path) == {"004"}


def test_migration_head_der_installation_ist_die_juengste_migration(srv):
    versions = _REPO / "backend" / "alembic" / "versions"
    newest = sorted(p for p in versions.glob("*.py") if p.name != "__init__.py")[-1]
    revision = re.search(r"""^revision[^=\n]*=\s*['"]([^'"]+)""",
                         newest.read_text(encoding="utf-8"), re.M).group(1)
    assert srv.migration_heads(versions) == {revision}


def test_macos_nennt_launchctl(srv, inst, caplog, monkeypatch):
    monkeypatch.setattr(srv, "IS_MACOS", True)
    with caplog.at_level(logging.INFO, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst), FakeCluster())
    assert code == 0
    assert "launchctl load /Library/LaunchDaemons/de.praxiszeit.server.plist" in caplog.text
    assert "systemctl" not in caplog.text


# --- PostgreSQL nur fuer die Dauer des Vorgangs ------------------------------

def test_startet_postgresql_nur_fuer_den_vorgang(srv, inst):
    code, state = _restore(srv, _dump(inst), FakeCluster(), pg_running=False)
    assert code == 0
    assert state["started"] == 1 and state["stopped"] == 1


def test_laufendes_postgresql_bleibt_an(srv, inst):
    code, state = _restore(srv, _dump(inst), FakeCluster(), pg_running=True)
    assert code == 0
    assert state["started"] == 0 and state["stopped"] == 0


def test_stoppt_postgresql_auch_nach_einem_fehler(srv, inst):
    code, state = _restore(srv, _dump(inst), FakeCluster(fail_load=True), pg_running=False)
    assert code == 1
    assert state["started"] == 1 and state["stopped"] == 1


# --- Bestand bleibt bei jedem Fehler unberuehrt -------------------------------

def test_gescheitertes_einspielen_laesst_den_bestand_stehen(srv, inst, caplog):
    cluster = FakeCluster(fail_load=True)
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst), cluster)
    assert code == 1
    assert cluster.dbs == {"postgres": "", "praxiszeit": _OLD}
    assert "drop:praxiszeit" not in cluster.events
    assert 'relation "users" already exists' in caplog.text
    assert "unveraendert" in caplog.text


def test_backup_einer_neueren_version_laesst_den_bestand_stehen(srv, inst, caplog):
    """Diese Installation kennt die Revision nicht: der Dienststart fiele an
    „Can't locate revision“ — und der Bestand waere schon ersetzt."""
    cluster = FakeCluster(revision="074_aus_der_zukunft")
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst), cluster)
    assert code == 1
    assert cluster.dbs == {"postgres": "", "praxiszeit": _OLD}
    assert "074_aus_der_zukunft" in caplog.text
    assert "neueren" in caplog.text


def test_dump_ohne_praxiszeit_schema_laesst_den_bestand_stehen(srv, inst, caplog):
    cluster = FakeCluster(has_alembic=False)
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst), cluster)
    assert code == 1
    assert cluster.dbs == {"postgres": "", "praxiszeit": _OLD}
    assert "alembic_version" in caplog.text


def test_scheitert_die_umbenennung_bleiben_die_daten_erhalten(srv, inst, caplog):
    """Bestand schon entfernt, Umbenennen gescheitert: die eingespielten Daten
    liegen in der Zwischendatenbank — sie darf dann nicht weggeraeumt werden."""
    cluster = FakeCluster(fail_rename=True)
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst), cluster)
    assert code == 1
    assert cluster.dbs.get("praxiszeit_restore") == _DUMP
    assert "praxiszeit_restore" in caplog.text


def test_unterbrochener_tausch_raeumt_die_eingespielten_daten_nicht_weg(srv, inst):
    """Strg+C zwischen dem Entfernen des Bestands und dem Umbenennen: die
    Zwischendatenbank ist dann die einzige Kopie im Cluster."""
    cluster = FakeCluster(interrupt_rename=True)
    with pytest.raises(KeyboardInterrupt):
        _restore(srv, _dump(inst), cluster, pg_running=False)
    assert cluster.dbs.get("praxiszeit_restore") == _DUMP
    assert "drop:praxiszeit_restore" not in cluster.events[2:], cluster.events


def test_unvollstaendiger_dump_wird_vor_jeder_aenderung_abgelehnt(srv, inst, caplog):
    cluster = FakeCluster()
    truncated = _dump(inst, "--\n-- PostgreSQL database dump\n--\nCREATE TABLE users ();\n")
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, state = _restore(srv, truncated, cluster, pg_running=False)
    assert code == 1
    assert cluster.calls == []
    assert state["started"] == 0
    assert "unvollstaendig" in caplog.text
    assert not list((inst / "data").glob(".restore-*"))


def test_kein_gzip_wird_vor_jeder_aenderung_abgelehnt(srv, inst, caplog):
    cluster = FakeCluster()
    plain = inst / "data" / "backups" / "kaputt.sql.gz"
    plain.write_text(_DUMP, encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, state = _restore(srv, plain, cluster, pg_running=False)
    assert code == 1
    assert cluster.calls == []
    assert state["started"] == 0
    assert not list((inst / "data").glob(".restore-*"))


def test_fehlende_datei(srv, inst, caplog):
    cluster = FakeCluster()
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, inst / "gibt-es-nicht.sql.gz", cluster)
    assert code == 1
    assert cluster.calls == []
    assert "nicht gefunden" in caplog.text


# --- Vorbedingungen ----------------------------------------------------------

@pytest.mark.parametrize("macos,stop", [
    (False, "systemctl stop praxiszeit"),
    (True, "launchctl unload /Library/LaunchDaemons/de.praxiszeit.server.plist"),
])
def test_laufender_dienst_wird_nicht_angefasst(srv, inst, caplog, monkeypatch, macos, stop):
    """Der laufende Prozess arbeitete sonst gegen den eingespielten Stand, und
    erst sein naechster Start migrierte — genau der Fehler der alten Anleitung."""
    monkeypatch.setattr(srv, "IS_MACOS", macos)
    (inst / "data" / "praxiszeit.pid").write_text(str(os.getpid()), encoding="utf-8")
    cluster = FakeCluster()
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, state = _restore(srv, _dump(inst), cluster, pg_running=True)
    assert code == 1
    assert cluster.calls == []
    assert state["started"] == 0 and state["stopped"] == 0
    assert stop in caplog.text


def test_veraltete_pid_datei_haelt_nicht_auf(srv, inst):
    (inst / "data" / "praxiszeit.pid").write_text("999999999", encoding="utf-8")
    code, _ = _restore(srv, _dump(inst), FakeCluster())
    assert code == 0


def test_fremder_prozess_mit_der_pid_gilt_als_laufend(srv, inst, monkeypatch):
    """Darf dieses Konto den Prozess nicht signalisieren, existiert er trotzdem
    (``_read_pid`` sieht darin „kein Prozess“)."""
    (inst / "data" / "praxiszeit.pid").write_text("4242", encoding="utf-8")

    def _kill(pid, sig):
        raise PermissionError

    monkeypatch.setattr(srv.os, "kill", _kill)
    cluster = FakeCluster()
    code, _ = _restore(srv, _dump(inst), cluster)
    assert code == 1
    assert cluster.calls == []


def test_root_ohne_postgresql_nennt_den_aufruf_als_dienstkonto(srv, inst, caplog, monkeypatch):
    monkeypatch.setattr(srv, "_running_as_root", lambda: True)
    dump = _dump(inst)
    cluster = FakeCluster()
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, state = _restore(srv, dump, cluster, pg_running=False)
    assert code == 1
    assert state["started"] == 0
    assert cluster.calls == []
    assert caplog.text.rstrip().endswith(
        f"sudo -u dienstkonto /inst/bin/python/bin/python3 {_SERVER_PATH} restore {dump}"
    ), caplog.text


def test_ohne_zugangsdaten(srv, inst, caplog, monkeypatch):
    monkeypatch.setattr(srv, "pg_load_credentials", lambda: (None, None))
    cluster = FakeCluster()
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst), cluster)
    assert code == 1
    assert cluster.calls == []
    assert ".db-credentials" in caplog.text


def test_windows_verweist_auf_restore_backup_bat(srv, inst, caplog, monkeypatch):
    monkeypatch.setattr(srv, "IS_WINDOWS", True)
    cluster = FakeCluster()
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst), cluster)
    assert code == 1
    assert cluster.calls == []
    assert "restore-backup.bat" in caplog.text


def test_parser_kennt_den_unterbefehl(srv):
    with patch("sys.argv", ["praxiszeit-server.py", "restore", "data/backups/x.sql.gz"]), \
         patch.object(srv, "cmd_restore") as handler:
        srv.main()
    assert handler.called
    assert handler.call_args[0][0].file == "data/backups/x.sql.gz"


# --- Bekannte Revisionen ------------------------------------------------------

def test_kennt_alle_revisionen_der_installation(srv):
    versions = _REPO / "backend" / "alembic" / "versions"
    known = srv.known_migration_revisions(versions)
    files = [p for p in versions.glob("*.py") if p.name != "__init__.py"]
    # Je Migrationsdatei genau eine Revision — sonst fehlt eine im Muster.
    assert len(known) == len(files)
    assert {"001", "011", "071_security_events", "073_work_blocks"} <= known


# --- Anleitungen ---------------------------------------------------------------

def _native_restore_section() -> str:
    text = (_REPO / "docs" / "BACKUP.md").read_text(encoding="utf-8")
    start = text.index("## Restore (Wiederherstellung)")
    native = text.index("### Native", start)
    return text[native:text.index("### Docker", native)]


def test_backup_md_nativ_haelt_den_dienst_an_und_startet_ihn_neu():
    section = _native_restore_section()
    # Weder bei laufendem Dienst noch ohne Abbruch beim ersten Fehler von Hand
    # in die bestehende Datenbank (der alte Weg).
    assert '| "$PZ/bin/postgresql/bin/psql"' not in section, section
    for stop, restore, start in (
        ("sudo systemctl stop praxiszeit",
         "sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 /opt/praxiszeit/praxiszeit-server.py restore",
         "sudo systemctl start praxiszeit"),
        ("sudo launchctl unload /Library/LaunchDaemons/de.praxiszeit.server.plist",
         "sudo -u _praxiszeit /usr/local/praxiszeit/bin/python/bin/python3 /usr/local/praxiszeit/praxiszeit-server.py restore",
         "sudo launchctl load /Library/LaunchDaemons/de.praxiszeit.server.plist"),
    ):
        assert stop in section and restore in section and start in section, section
        assert section.index(stop) < section.index(restore) < section.index(start), section


def _update_rollback_section() -> str:
    text = (_REPO / "docs" / "UPDATE.md").read_text(encoding="utf-8")
    start = text.index("## Rollback")
    return text[start:]


def test_update_md_rollback_legt_app_vor_dem_alten_paket_beiseite():
    """Gesamtreview 1.20, Runde 2: install.sh (``cp -r app/* …/app/``), der
    macOS-Installer (``cp -R app``) und der Windows-Update-Wizard (robocopy
    ``/E`` ohne ``/PURGE``) mischen das neue ``app/`` ueber das alte. Beim
    Rollback blieb 073 in ``alembic/versions`` liegen, der Start von 1.19.3
    wandte sie erneut an → der Start bricht ab (UndefinedColumn). Die Anleitung legt
    ``app/`` deshalb nach dem Einspielen und vor dem alten Paket beiseite."""
    section = _update_rollback_section()
    for stop, restore, move in (
        ("sudo systemctl stop praxiszeit",
         "sudo -u praxiszeit /opt/praxiszeit/bin/python/bin/python3 /opt/praxiszeit/praxiszeit-server.py restore",
         "sudo mv /opt/praxiszeit/app /opt/praxiszeit/app.neu-$(date +%F)"),
        ("sudo launchctl unload /Library/LaunchDaemons/de.praxiszeit.server.plist",
         "sudo -u _praxiszeit /usr/local/praxiszeit/bin/python/bin/python3 /usr/local/praxiszeit/praxiszeit-server.py restore",
         "sudo mv /usr/local/praxiszeit/app /usr/local/praxiszeit/app.neu-$(date +%F)"),
    ):
        assert stop in section and restore in section and move in section, section
        assert section.index(stop) < section.index(restore) < section.index(move), section
    # Windows: erst app umbenennen und das alte Paket einspielen, dann dessen
    # restore-backup.bat (es startet den Dienst am Ende selbst).
    bat = section[section.index("```bat"):]
    bat = bat[:bat.index("```", 3)]
    steps = ("net stop PraxisZeit", "ren app app.neu", "update-wizard.bat",
             "restore-backup.bat data\\backups\\")
    for step in steps:
        assert step in bat, (step, bat)
    assert [bat.index(s) for s in steps] == sorted(bat.index(s) for s in steps), bat
    # Der alte Satz stimmte nur bei komplett ersetztem app/.
    assert "Andersherum scheitert schon der\nStart der alten Version" not in section


def test_die_anderen_anleitungen_nennen_den_unterbefehl():
    for name in ("docs/setup-anleitung.md", "docs/INSTALL-NATIVE.md", "docs/UPDATE.md"):
        text = (_REPO / name).read_text(encoding="utf-8")
        assert "praxiszeit-server.py restore" in text, name
    setup = (_REPO / "docs" / "setup-anleitung.md").read_text(encoding="utf-8")
    assert "muss beim\nEinspielen **laufen**" not in setup

