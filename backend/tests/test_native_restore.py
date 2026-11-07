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
``restore-backup.bat`` unter Windows hatte dieselben Luecken (Tests am Ende
der Datei).

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
import json
import logging
import os
import re
import subprocess
import sys
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
# SECRET_KEY der Test-Installation: jede Sicherung, die PraxisZeit schreibt,
# traegt eine Signaturzeile (Fix-Runde S3-03).
_KEY = "test-secret-key-0123456789abcdef0123456789abcdef"


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("praxiszeit_server_restore", _SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _fresh_pg_port(srv):
    """pg_port() is memoized per process; every test starts uncached."""
    srv.pg_port.cache_clear()
    yield
    srv.pg_port.cache_clear()


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
        self.roles: set[str] = set()
        self.role_sql: list[str] = []
        # Katalog der Zwischendatenbank fuer den Funktionsabgleich (Runde 4/6)
        self.routines = {"functions": [], "triggers": [], "other": [], "extensions": [],
                         "tables": []}
        # Ausgabe des RLS-Vergleichsskripts (Runde 6)
        self.rls_deparsed = {"expected": [], "found": []}
        self.rls_scripts: list[str] = []
        self.fail_acl_reset = False

    def __call__(self, cmd, **kw):
        if Path(cmd[0]).name != "psql":
            raise AssertionError(f"unerwarteter Aufruf: {cmd}")
        self.calls.append(list(cmd))
        self.envs.append(kw.get("env") or {})
        db = cmd[cmd.index("-d") + 1]
        if db not in self.dbs:
            return subprocess.CompletedProcess(cmd, 2, "", f'FATAL: database "{db}" does not exist')
        out = []
        if "-f" in cmd and cmd[cmd.index("-f") + 1] == "-":
            if "pz_rls_" in (kw.get("input") or ""):
                # RLS-Vergleichsskript (Runde 6)
                self.events.append(f"rls:{db}")
                self.rls_scripts.append(kw["input"])
                return subprocess.CompletedProcess(cmd, 0, json.dumps(self.rls_deparsed) + "\n", "")
            # Skript ueber stdin (Ladrolle mit Passwort, Runde 3).
            for sql in (kw.get("input") or "").split(";\n"):
                sql = sql.strip()
                if sql:
                    self._role_sql(sql)
            return subprocess.CompletedProcess(cmd, 0, "", "")
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
            elif sql.startswith(("CREATE ROLE", "DROP ROLE")):
                self._role_sql(sql)
            elif sql.startswith("GRANT CREATE ON SCHEMA public"):
                self.events.append(f"grantload:{db}")
            elif sql.startswith("DO $pz_acl$"):
                # Rechte der Zwischendatenbank zuruecksetzen (Runde 7)
                self.events.append(f"aclreset:{db}")
                if self.fail_acl_reset:
                    return subprocess.CompletedProcess(cmd, 1, "", "ERROR:  revoke failed\n")
            elif sql.startswith("REASSIGN OWNED"):
                self.events.append(f"reassign:{db}")
            elif sql.startswith("DROP OWNED"):
                pass
            elif "alembic_version" in sql:
                self.events.append(f"revision:{db}")
                if not self.has_alembic:
                    return subprocess.CompletedProcess(
                        cmd, 1, "", 'ERROR:  relation "alembic_version" does not exist\n')
                out.append(f"{self.revision}\n")
            elif "pg_proc" in sql:
                self.events.append(f"routines:{db}")
                out.append(json.dumps(self.routines) + "\n")
            elif "pg_database" in sql:
                name = re.search(r"datname = '([^']+)'", sql).group(1)
                out.append("1\n" if name in self.dbs else "")
            else:
                raise AssertionError(f"unerwartetes SQL: {sql}")
        return subprocess.CompletedProcess(cmd, 0, "".join(out), "")

    def _role_sql(self, sql: str) -> None:
        name = re.findall(r'"([^"]+)"', sql)[0]
        if sql.startswith("CREATE ROLE"):
            self.role_sql.append(sql)
            self.events.append(f"createrole:{name}")
            self.roles.add(name)
        elif sql.startswith("DROP ROLE"):
            self.events.append(f"droprole:{name}")
            self.roles.discard(name)
        else:
            raise AssertionError(f"unerwartetes SQL: {sql}")


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
    monkeypatch.setattr(srv, "load_config", lambda: {"security": {"secret_key": _KEY}})
    monkeypatch.setattr(srv, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(srv, "pg_load_credentials", lambda: ("su-pw", "app-pw"))
    monkeypatch.setattr(srv, "_running_as_root", lambda: False)
    monkeypatch.setattr(srv, "_install_owner", lambda: "dienstkonto")
    monkeypatch.setattr(srv, "bundled_python", lambda: "/inst/bin/python/bin/python3")
    return tmp_path


def _loaded(text: str) -> str:
    """Was psql bekommt (S3-03): eigene ``\\restrict``-Zeile mit Zufallsschluessel
    vorn, die restrict-Zeilen des Dumps entfernt - sonst unveraendert."""
    first, rest = text.split("\n", 1)
    assert re.fullmatch(r"\\restrict [0-9a-f]{48}", first), first
    return rest


def _signed(text: str, key: str = _KEY) -> str:
    """Wie ``backup`` die Sicherung schreibt: Signaturzeile am Ende."""
    spec = importlib.util.spec_from_file_location("praxiszeit_server_sign", _SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    signer = module.BackupMac(key)
    signer.update(text.encode("utf-8"))
    return text + signer.trailer().decode("ascii")


# Nur mit Repo berechnen: ohne praxiszeit-server.py (Backend-Container) ist das
# Modul per ``pytestmark`` uebersprungen, die Sammlung darf aber nicht scheitern.
_DUMP_LOADED = "".join(
    line for line in _signed(_DUMP).splitlines(keepends=True)
    if not line.startswith(("\\restrict ", "\\unrestrict "))
) if _SERVER_PATH.exists() else ""


def _dump(inst: Path, text: str = _DUMP, name: str = "praxiszeit_20261017_120000.sql.gz",
          *, key: str | None = _KEY) -> Path:
    path = inst / "data" / "backups" / name
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(_signed(text, key) if key else text)
    return path


def _restore(srv, file: Path, cluster: FakeCluster, *, pg_running=True, caplog=None,
             force_unverified=False):
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
            srv.cmd_restore(argparse.Namespace(file=str(file), force_unverified=force_unverified))
        except SystemExit as exc:
            code = exc.code
    return code, state


# --- Ablauf -------------------------------------------------------------------

def test_restore_ersetzt_die_datenbank_durch_das_backup(srv, inst):
    cluster = FakeCluster()
    code, _ = _restore(srv, _dump(inst), cluster)
    assert code == 0
    assert set(cluster.dbs) == {"postgres", "praxiszeit"}
    assert _loaded(cluster.dbs["praxiszeit"]) == _DUMP_LOADED


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
    assert _loaded(cluster.dbs["praxiszeit"]) == _DUMP_LOADED


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
    """Der Head ist das letzte Glied der Kette von der ersten Migration an - in
    KETTEN-Reihenfolge, nicht nach Dateinamen: die Datumsvorsilbe sortiert nicht
    immer wie die Kette (075 ist auf den 10.11. datiert, 076 auf den 7.11.)."""
    versions = _REPO / "backend" / "alembic" / "versions"
    rev_re = re.compile(r"""^revision[^=\n]*=\s*['"]([^'"]+)""", re.M)
    down_re = re.compile(r"^down_revision\b[^=\n]*=(.*)$", re.M)
    children: dict = {}
    files = [p for p in versions.glob("*.py") if p.name != "__init__.py"]
    for path in files:
        text = path.read_text(encoding="utf-8")
        rev = rev_re.search(text).group(1)
        parents = re.findall(r"""['"]([^'"]+)['"]""", down_re.search(text).group(1))
        for parent in parents or [None]:
            children.setdefault(parent, []).append(rev)
    chain, current = [], None
    while current in children:
        assert len(children[current]) == 1, (current, children[current])  # keine Verzweigung
        current = children[current][0]
        chain.append(current)
    assert len(chain) == len(files)  # jede Datei liegt auf der Kette
    assert srv.migration_heads(versions) == {chain[-1]}


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
    assert _loaded(cluster.dbs.get("praxiszeit_restore")) == _DUMP_LOADED
    assert "praxiszeit_restore" in caplog.text


def test_unterbrochener_tausch_raeumt_die_eingespielten_daten_nicht_weg(srv, inst):
    """Strg+C zwischen dem Entfernen des Bestands und dem Umbenennen: die
    Zwischendatenbank ist dann die einzige Kopie im Cluster."""
    cluster = FakeCluster(interrupt_rename=True)
    with pytest.raises(KeyboardInterrupt):
        _restore(srv, _dump(inst), cluster, pg_running=False)
    assert _loaded(cluster.dbs.get("praxiszeit_restore")) == _DUMP_LOADED
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


# --- Windows: restore-backup.bat ---------------------------------------------
#
# Gesamtreview 1.20, Runde 2: derselbe Fehler wie beim alten Linux-Weg. Kein
# psql-Aufruf setzte ON_ERROR_STOP, kein Schritt pruefte den errorlevel, das
# Entpacken pruefte nur, ob die Zieldatei existiert (ein abgeschnittenes .gz
# laesst Python mit EOFError abbrechen, die angefangene .sql-Datei liegt aber
# da und wurde eingespielt), DROP lief ohne FORCE und ungeprueft (scheitert
# es, scheitert CREATE, und der Dump laeuft in die alte Datenbank). Am Ende
# startete das Script den Dienst bedingungslos und meldete „Restore
# abgeschlossen!" — fuer ein von NAS/USB nur teilweise kopiertes Backup eine
# halbe Datenbank, auf der beim Dienststart alembic und der Bootstrap liefen.
# cmd.exe gibt es hier nicht; die Tests pruefen den Aufbau des Scripts.

_BAT = _REPO / "installer" / "windows" / "restore-backup.template.bat"


def _bat_text() -> str:
    return _BAT.read_bytes().decode("ascii")


def _bat_lines() -> list[str]:
    return _bat_text().split("\r\n")


def _bat_blocks() -> dict[str, list[str]]:
    """Zeilen je Sprungmarke; ``""`` = Hauptteil bis zur ersten Marke."""
    blocks: dict[str, list[str]] = {"": []}
    current = ""
    for line in _bat_lines():
        if line.startswith(":") and not line.startswith("::"):
            current = line[1:].strip().lower()
            blocks[current] = []
        else:
            blocks[current].append(line.strip())
    return blocks


def test_restore_bat_hat_durchgehend_crlf():
    # Mit LF findet cmd.exe die Sprungmarken nicht (setup.bat, #286).
    raw = _BAT.read_bytes()
    assert b"\n" not in raw.replace(b"\r\n", b""), "restore-backup.template.bat braucht CRLF"


def test_restore_bat_prueft_jeden_schritt():
    main = _bat_blocks()[""]
    commands = [i for i, line in enumerate(main)
                if line.startswith(('"%PSQL%"', '"%PYTHON%"'))]
    assert len(commands) >= 6, main
    for i in commands:
        assert "%PSQL_ARGS%" in main[i] or main[i].startswith('"%PYTHON%"'), main[i]
        follow = next(line for line in main[i + 1:] if line and not line.upper().startswith("REM"))
        if "prepare-restore-dump" in main[i]:
            # Exit 0/4 weiter, 2 = Signatur, alles andere = abgelehnt (Runde 4)
            assert follow == 'SET "PREP_RC=%ERRORLEVEL%"', (main[i], follow)
            continue
        assert follow.lower().startswith("if errorlevel 1"), (main[i], follow)
    args = next(line for line in main if line.startswith('SET "PSQL_ARGS='))
    assert "-v ON_ERROR_STOP=1" in args and "-w" in args.split(), args


def test_restore_bat_prueft_das_backup_vor_jeder_aenderung():
    text = _bat_text()
    check = text.index("PostgreSQL database dump complete")
    assert check < text.index("net stop PraxisZeit")
    assert check < text.index("DROP DATABASE")
    # Entpacken ueber argv, nicht ueber in den Python-Code eingesetzte Pfade.
    unpack = next(line for line in _bat_lines() if "gzip" in line and '"%PYTHON%"' in line)
    assert unpack.rstrip().endswith('"%BACKUP_GZ%" "%BACKUP_DUMP%"'), unpack
    assert "r'%BACKUP_GZ%'" not in text


def test_restore_bat_ersetzt_die_datenbank_erst_nach_dem_einspielen():
    text = _bat_text()
    assert 'SET "RESTORE_DB=praxiszeit_restore"' in text
    # Anlegen, Einspielen und Standpruefung macht load-restore-db (Runde 4)
    load = text.index('praxiszeit-server.py" load-restore-db %LOAD_FLAGS% "%BACKUP_DUMP%"')
    assert text[load:load + 200].split("\r\n")[1] == "if errorlevel 1 goto :bestand_unveraendert"
    drop = text.index("DROP DATABASE IF EXISTS praxiszeit WITH (FORCE)")
    rename = text.index("ALTER DATABASE %RESTORE_DB% RENAME TO praxiszeit")
    grants = text.index("init-db-user.sql")
    assert load < drop < rename < grants
    assert "DROP DATABASE IF EXISTS praxiszeit;" not in text
    # nie mehr selbst als Superuser einspielen
    assert '-f "%BACKUP_DUMP%"' not in text


def test_restore_bat_startet_den_dienst_nur_nach_erfolg():
    blocks = _bat_blocks()
    main = blocks[""]
    # Der Anwendungsdienst "PraxisZeit" - nicht der Datenbankdienst
    # "PraxisZeit-PostgreSQL", den das Script vor dem Einspielen startet.
    starts = [i for i, line in enumerate(main) if line.lower().split()[:3] == ["net", "start", "praxiszeit"]]
    assert len(starts) == 1, main
    grants = next(i for i, line in enumerate(main) if "init-db-user.sql" in line)
    assert grants < starts[0]
    success = next(i for i, line in enumerate(main) if "Restore abgeschlossen" in line)
    assert starts[0] < success
    assert any(line.lower() == "exit /b 0" for line in main[success:])
    targets = {line.split("goto :", 1)[1].split()[0].lower()
               for line in _bat_lines() if "goto :" in line.lower()}
    assert targets, "keine Fehlerpfade"
    for label in targets:
        block = blocks[label]
        assert not any(line.lower().startswith("net start") for line in block), (label, block)
        assert not any("Restore abgeschlossen" in line for line in block), (label, block)
        ends = [line.lower() for line in block if line.lower().startswith(("exit /b", "goto :"))]
        assert ends and (ends[-1] == "exit /b 1" or ends[-1].startswith("goto :")), (label, block)


# Gesamtreview 1.20, Runde 3: ein Backup einer NEUEREN Version lief durch die
# .bat (DROP, RENAME, ``net start`` - und der Dienst brach an „Can't locate
# revision“ ab). Review-Runde 4: die .bat spielt ueber ``load-restore-db`` ein,
# also ueber denselben Code wie ``restore`` (``_load_into_restore_db``):
# Standpruefung vor dem Tausch, unverifizierte Sicherungen als Ladrolle ohne
# Superuser-Rechte, Funktionen und Trigger gegen die Migrationen.

def _load_cmd(srv, cluster, file: Path, *, restricted: bool, capsys):
    code = 0
    with patch.object(srv.subprocess, "run", side_effect=cluster):
        try:
            srv.cmd_load_restore_db(argparse.Namespace(file=str(file), restricted=restricted))
        except SystemExit as exc:
            code = exc.code
    return code, capsys.readouterr()


def test_restore_bat_laedt_unverifiziert_als_ladrolle(srv, inst, capsys):
    """Exit 4 von prepare-restore-dump --restricted-load setzt --restricted."""
    text = _bat_text()
    prep = text.index('prepare-restore-dump %PREP_FLAGS% --restricted-load "%BACKUP_DUMP%"')
    block = text[prep:text.index("echo OK.", prep)]
    assert 'if "%PREP_RC%"=="4" SET "LOAD_FLAGS=--restricted"' in block
    assert 'if "%PREP_RC%"=="2" goto :backup_unsigniert' in block
    assert 'if not "%PREP_RC%"=="0" if not "%PREP_RC%"=="4" goto :backup_abgelehnt' in block
    assert block.index('SET "LOAD_FLAGS="') < block.index('"%PREP_RC%"=="4"')
    dump = inst / "data" / "d.sql"
    dump.write_text(_HEAD + "ALTER TABLE public.t OWNER TO praxiszeit;\n" + _TAIL, encoding="utf-8")
    # unsigniert + --force-unverified -> Exit 4, Eigentuemer-Zeilen entfernt
    with pytest.raises(SystemExit) as exc:
        srv.cmd_prepare_restore_dump(argparse.Namespace(
            file=str(dump), force_unverified=True, restricted_load=True))
    assert exc.value.code == srv.PREPARE_EXIT_UNVERIFIED == 4
    assert " OWNER TO " not in dump.read_text(encoding="utf-8")
    cluster = FakeCluster(revision="073_work_blocks")
    code, out = _load_cmd(srv, cluster, dump, restricted=True, capsys=capsys)
    assert code == 0 and out.out.strip() == "073_work_blocks"
    load = next(c for c in cluster.calls if "-f" in c and c[c.index("-f") + 1] == str(dump))
    assert load[load.index("-U") + 1] == srv.RESTORE_LOAD_ROLE
    assert "routines:praxiszeit_restore" in cluster.events
    assert cluster.roles == set() and cluster.dbs["praxiszeit"] == _OLD  # kein Tausch hier
    # signiert: Exit 0, als Superuser
    signed = inst / "data" / "e.sql"
    signed.write_text(_signed(_HEAD + _TAIL), encoding="utf-8")
    srv.cmd_prepare_restore_dump(argparse.Namespace(
        file=str(signed), force_unverified=True, restricted_load=True))
    cluster = FakeCluster(revision="073_work_blocks")
    code, _ = _load_cmd(srv, cluster, signed, restricted=False, capsys=capsys)
    assert code == 0 and cluster.role_sql == []
    assert "routines:praxiszeit_restore" not in cluster.events


def test_restore_bat_lehnt_ein_backup_einer_neueren_version_vor_dem_tausch_ab(srv, inst, capsys):
    dump = inst / "data" / "d.sql"
    dump.write_text(_HEAD + _TAIL, encoding="utf-8")
    cluster = FakeCluster(revision="074_aus_der_zukunft")
    code, out = _load_cmd(srv, cluster, dump, restricted=False, capsys=capsys)
    assert code == 1
    fehler = [line for line in out.err.splitlines() if line.startswith("FEHLER: ")]
    assert fehler and "074_aus_der_zukunft" in fehler[0] and "neueren PraxisZeit-Version" in fehler[0]
    assert cluster.dbs["praxiszeit"] == _OLD


def test_restore_bat_ohne_alembic_version_lehnt_ab(srv, inst, capsys):
    dump = inst / "data" / "d.sql"
    dump.write_text(_HEAD + _TAIL, encoding="utf-8")
    code, out = _load_cmd(srv, FakeCluster(has_alembic=False), dump, restricted=True, capsys=capsys)
    assert code == 1 and "keine PraxisZeit-Datenbank" in out.err


def test_restore_bat_ohne_migrationen_lehnt_ab(srv, inst, capsys):
    for p in (inst / "app" / "backend" / "alembic" / "versions").glob("x_*.py"):
        p.unlink()
    dump = inst / "data" / "d.sql"
    dump.write_text(_HEAD + _TAIL, encoding="utf-8")
    code, out = _load_cmd(srv, FakeCluster(), dump, restricted=False, capsys=capsys)
    assert code == 1 and "Installation unvollstaendig" in out.err


def test_parser_kennt_load_restore_db(srv, monkeypatch):
    seen = {}
    monkeypatch.setattr(srv, "cmd_load_restore_db", lambda a: seen.setdefault("load", a))
    monkeypatch.setattr(sys, "argv", ["x", "load-restore-db", "--restricted", "/tmp/b.sql"])
    srv.main()
    assert seen["load"].restricted is True and seen["load"].file == "/tmp/b.sql"


# --- Windows: Datenbank-Port (Teil C) ----------------------------------------

def test_restore_bat_reads_db_port_from_server_script():
    text = _bat_text()
    assert "print-db-port" in text
    assert 'SET "DB_PORT=' in text
    args = next(line for line in _bat_lines() if line.startswith('SET "PSQL_ARGS='))
    assert "-h localhost" in args and "-p %DB_PORT%" in args and "5432" not in args, args


def test_restore_bat_syncs_port_before_cluster_start():
    lines = _bat_lines()
    sync = next(i for i, line in enumerate(lines) if "sync-db-port" in line and '"%PYTHON%"' in line)
    start = next(i for i, line in enumerate(lines)
                 if line.startswith('"%PG_CTL%"') and " start" in line)
    assert sync < start


def test_restore_bat_starts_pg_service_after_port_sync():
    """Windows 11: sync-db-port stops PraxisZeit-PostgreSQL after a port change,
    and the script's own pg_ctl start fails as administrator ("Access is
    denied"). The service must be started again before the first psql."""
    lines = _bat_lines()
    sync = next(i for i, line in enumerate(lines) if "sync-db-port" in line and '"%PYTHON%"' in line)
    svc = next(i for i, line in enumerate(lines) if line.startswith("net start PraxisZeit-PostgreSQL"))
    start = next(i for i, line in enumerate(lines)
                 if line.startswith('"%PG_CTL%"') and " start" in line)
    first_psql = next(i for i, line in enumerate(lines) if line.startswith('"%PSQL%"'))
    assert sync < svc < start < first_psql
    assert lines[svc].rstrip().endswith(">nul 2>&1"), lines[svc]


def test_restore_bat_sets_psql_args_after_db_port():
    lines = _bat_lines()
    port = next(i for i, line in enumerate(lines) if line.startswith('for /f') and "print-db-port" in line)
    args = next(i for i, line in enumerate(lines) if line.startswith('SET "PSQL_ARGS='))
    assert port < args
    assert lines[port].count('(`""%PYTHON%"') == 1, lines[port]
    assert 'SET "DB_PORT="' in lines[:port]


# --- Audit 2026-11-07 S3-03: nur Dumps einspielen, wie pg_dump sie schreibt ---
#
# psql fuehrt Backslash-Befehle aus dem Dump aus (\! cmd, \o |cmd, \copy ...
# program) - als Superuser, unter Windows als Administrator. Gepruefter Weg:
# Lexer-Pruefung mit verstaendlicher Meldung + eigener \restrict-Schluessel
# in der ersten Zeile (psql lehnt dann jeden weiteren Backslash-Befehl ab).

_HEAD = "--\n-- PostgreSQL database dump\n--\n\\restrict abc\nSET standard_conforming_strings = on;\n"
_TAIL = "--\n-- PostgreSQL database dump complete\n--\n\n\\unrestrict abc\n\n"


def _check(srv, tmp_path, body: str):
    p = tmp_path / "d.sql"
    p.write_text(_HEAD + body + _TAIL, encoding="utf-8")
    srv.validate_restore_dump(p)


@pytest.mark.parametrize("body", [
    "\\! calc.exe\n",
    "   \\! calc.exe\n",
    "SELECT 1; \\! calc.exe\n",
    "SELECT 1 \\g |calc\n",
    "\\o |powershell -c x\n",
    "\\copy users to program 'x'\n",
    "\\connect postgres\n",
    "\\set ON_ERROR_STOP 0\n",
    "\\restrict abc extra\n",
    # Bezeichner + normale Zeichenkette (keine E-Zeichenkette): psql schliesst
    # am zweiten Hochkomma, danach steht der Befehl ausserhalb der Kette.
    "SELECT xe'\\'; \\! calc --'\n",
    # foo$$ ist ein Bezeichner, keine Dollar-Quote.
    "SELECT foo$$; \\! calc\n",
    "COMMENT ON TABLE t IS 'a';\n\\! calc\n",
    "CREATE TABLE t (\n  a text -- kommentar\n);\n\\! calc\n",
])
def test_dump_mit_psql_befehl_wird_abgelehnt(srv, tmp_path, body):
    with pytest.raises(srv.RestoreError, match="psql-Befehl|gehoert nicht"):
        _check(srv, tmp_path, body)


@pytest.mark.parametrize("body", [
    "CREATE ROLE boese SUPERUSER;\n",
    "ALTER ROLE praxiszeit_app BYPASSRLS;\n",
    "alter\n  role praxiszeit_app bypassrls;\n",
    "ALTER SYSTEM SET archive_command = 'calc';\n",
    "COPY users TO PROGRAM 'calc';\n",
    "copy (select 1) to program 'calc';\n",
    "CREATE EVENT TRIGGER t ON ddl_command_start EXECUTE FUNCTION f();\n",
    "CREATE FUNCTION f() RETURNS int AS '/tmp/x.so', 'f' LANGUAGE C;\n",
    "LOAD '/tmp/x.so';\n",
    # Final-Review (S3-03-Rest): Daten-Anweisungen und Katalog-Schreibzugriffe
    # kamen auf dem --force-unverified-Weg durch (pg_authid ist clusterweit und
    # ueberlebt den Datenbanktausch).
    "UPDATE pg_catalog.pg_authid SET rolsuper=true, rolbypassrls=true WHERE rolname='praxiszeit_app';\n",
    "INSERT INTO pg_catalog.pg_auth_members (roleid, member, grantor) VALUES (10, 16384, 10);\n",
    "CREATE FUNCTION f() RETURNS void LANGUAGE sql AS "
    "'UPDATE pg_catalog.pg_authid SET rolsuper=true; SELECT 1';\n",
    "CREATE FUNCTION f() RETURNS void LANGUAGE sql AS $$UPDATE /**/ pg_authid SET rolsuper=true$$;\n",
    "CREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS "
    "$$BEGIN PERFORM '--'; UPDATE /*x*/ pg_authid SET rolsuper=true; END$$;\n",
    "CREATE FUNCTION f() RETURNS void LANGUAGE sql AS $$UPDATE --x\n pg_authid SET rolsuper=true$$;\n",
    "CREATE FUNCTION f() RETURNS int LANGUAGE sql BEGIN ATOMIC "
    "UPDATE pg_catalog.pg_authid SET rolsuper=true; SELECT 1; END;\n",
    "WITH x AS (UPDATE public.users SET role='admin' RETURNING 1) SELECT 1;\n",
    "DELETE FROM public.users;\n",
    "INSERT INTO t VALUES (1) ON CONFLICT DO NOTHING;\n",
    "TRUNCATE public.time_entry_audit_logs;\n",
    "EXPLAIN ANALYZE UPDATE pg_authid SET rolsuper=true;\n",
    "CREATE RULE r AS ON INSERT TO public.t DO ALSO UPDATE pg_catalog.pg_authid SET rolsuper=true;\n",
    'ALTER TABLE pg_catalog."pg_authid" OWNER TO praxiszeit_app;\n',
])
def test_dump_mit_fremder_anweisung_wird_abgelehnt(srv, tmp_path, body):
    with pytest.raises(srv.RestoreError, match="pg_dump nie"):
        _check(srv, tmp_path, body)


def test_echter_dump_mit_copy_daten_und_literalen_geht_durch(srv, tmp_path):
    body = (
        "CREATE TABLE public.t (a text, b text);\n"
        "COMMENT ON TABLE public.t IS 'Pfad C:\\Daten\\x; \\! kein Befehl';\n"
        "CREATE FUNCTION public.f() RETURNS text\n    LANGUAGE plpgsql\n"
        "    AS $_$\nBEGIN\n  RETURN '\\! auch kein Befehl';\nEND;\n$_$;\n"
        "CREATE POLICY p ON public.t USING ((a = current_setting('app.x'::text, true)));\n"
        "/* block \\! kommentar /* verschachtelt */ */\n"
        "COMMENT ON COLUMN public.t.a IS E'\\'\\\\';\n"
        "COPY public.t (a, b) FROM stdin;\n"
        "\\N\t\\\\! Daten mit Backslash\n"
        "\\! sieht aus wie ein Befehl, ist aber eine Datenzeile\n"
        "\\.\n"
        "SELECT pg_catalog.setval('public.t_id_seq', 1, false);\n"
    )
    _check(srv, tmp_path, body)  # wirft nicht


def test_lesende_katalogabfrage_im_trigger_und_erweiterung_gehen_durch(srv, tmp_path):
    """Gegenprobe: die Trigger von PraxisZeit (Migration 076, RLS-Wächter) LESEN
    pg_class/pg_roles im Rumpf, und pg_dump schreibt pg_trgm als Erweiterung —
    beides bleibt erlaubt."""
    body = (
        "CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;\n"
        "COMMENT ON EXTENSION pg_trgm IS 'text similarity';\n"
        "CREATE FUNCTION public.pz_audit_guard() RETURNS trigger\n    LANGUAGE plpgsql\n"
        "    SET search_path TO 'public', 'pg_temp'\n    AS $$\nDECLARE tbl_owner oid;\nBEGIN\n"
        "    SELECT relowner INTO tbl_owner FROM pg_class WHERE oid = TG_RELID;\n"
        "    IF pg_has_role(current_user, tbl_owner, 'MEMBER')\n"
        "       OR COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), false) THEN\n"
        "        IF TG_OP = 'UPDATE' THEN RETURN NEW; END IF;\n    END IF;\n"
        "    RAISE EXCEPTION 'nur anfuegbar';\nEND;\n$$;\n"
        "-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: pg_database_owner\n"
    )
    _check(srv, tmp_path, body)  # wirft nicht


def test_copy_ohne_ende_wird_abgelehnt(srv, tmp_path):
    p = tmp_path / "d.sql"
    p.write_text(_HEAD + "COPY public.t (a) FROM stdin;\nx\n", encoding="utf-8")
    with pytest.raises(srv.RestoreError, match="COPY"):
        srv.validate_restore_dump(p)


def test_prepare_setzt_eigenen_restrict_schluessel(srv, tmp_path):
    p = tmp_path / "d.sql"
    p.write_text(_signed(_HEAD + "CREATE TABLE t ();\n" + _TAIL), encoding="utf-8")
    srv.prepare_restore_dump(p, secret_key=_KEY)
    first = p.read_text(encoding="utf-8").split("\n", 1)[0]
    text = p.read_text(encoding="utf-8")
    assert re.fullmatch(r"\\restrict [0-9a-f]{48}", first)
    # Die eigenen restrict-Zeilen des Dumps sind weg (ein zweites \restrict
    # waere im eingeschraenkten Modus ein Fehler), der Rest ist unveraendert.
    assert "\\restrict abc" not in text and "\\unrestrict abc" not in text
    assert text.count("\\restrict ") == 1
    assert "CREATE TABLE t ();" in text and "dump complete" in text
    assert oct(p.stat().st_mode & 0o777) == oct(0o600)
    p2 = tmp_path / "e.sql"
    p2.write_text(_signed(_HEAD + _TAIL), encoding="utf-8")
    srv.prepare_restore_dump(p2, secret_key=_KEY)
    assert p2.read_text(encoding="utf-8").split("\n", 1)[0] != first  # je Restore neu


def test_prepare_laesst_abgelehnten_dump_unveraendert(srv, tmp_path):
    p = tmp_path / "d.sql"
    original = _signed(_HEAD + "\\! calc\n" + _TAIL)
    p.write_text(original, encoding="utf-8")
    with pytest.raises(srv.RestoreError):
        srv.prepare_restore_dump(p, secret_key=_KEY)
    assert p.read_text(encoding="utf-8") == original
    assert sorted(x.name for x in tmp_path.iterdir()) == ["d.sql"]


def test_restore_lehnt_praeparierten_dump_vor_jeder_aenderung_ab(srv, inst, caplog):
    cluster = FakeCluster()
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, state = _restore(srv, _dump(inst, _HEAD + "\\! rm -rf /\n" + _TAIL), cluster)
    assert code == 1
    assert cluster.calls == []  # kein psql-Aufruf
    assert cluster.dbs["praxiszeit"] == _OLD
    assert "psql-Befehl" in caplog.text
    assert not list((inst / "data").glob(".restore-*"))


def test_prepare_restore_dump_unterbefehl(srv, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(srv, "load_config", lambda: {"security": {"secret_key": _KEY}})
    p = tmp_path / "d.sql"
    p.write_text(_signed(_HEAD + "\\! calc\n" + _TAIL), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        srv.cmd_prepare_restore_dump(argparse.Namespace(file=str(p), force_unverified=False))
    assert e.value.code == 1
    assert "FEHLER:" in capsys.readouterr().err
    p.write_text(_signed(_HEAD + _TAIL), encoding="utf-8")
    srv.cmd_prepare_restore_dump(argparse.Namespace(file=str(p), force_unverified=False))
    assert p.read_text(encoding="utf-8").startswith("\\restrict ")


# --- Audit 2026-11-07: restore-backup.bat (S3-03, S3-07, S3-09, S3-10) -------

def test_restore_bat_prueft_den_dump_vor_dem_einspielen():
    text = _bat_text()
    prep = text.index('praxiszeit-server.py" prepare-restore-dump %PREP_FLAGS% --restricted-load '
                      '"%BACKUP_DUMP%"')
    assert text.index("PostgreSQL database dump complete") < prep
    assert prep < text.index("net stop PraxisZeit")
    assert prep < text.index('load-restore-db %LOAD_FLAGS% "%BACKUP_DUMP%"')
    assert 'goto :backup_abgelehnt' in text[prep:prep + 400]
    block = _bat_blocks()["backup_abgelehnt"]
    assert 'del "%BACKUP_DUMP%" 2>nul' in block and "exit /b 1" in block


def test_restore_bat_verlangt_scram_vor_dem_ersten_psql():
    text = _bat_text()
    assert 'SET "PGREQUIREAUTH=scram-sha-256"' in text
    assert text.index('SET "PGREQUIREAUTH=scram-sha-256"') < text.index('"%PSQL%"')


def test_restore_bat_liest_zugangsdaten_auch_mit_leerzeichen_im_pfad():
    lines = [line for line in _bat_lines() if line.strip().lower().startswith("for /f")]
    creds = [line for line in lines if "CREDS_FILE" in line]
    assert creds == ['for /f "usebackq tokens=1,* delims==" %%a in ("%CREDS_FILE%") do (']


def test_restore_bat_nimmt_den_eigenen_ordner_als_standard():
    text = _bat_text()
    assert 'SET "DIR=%~dp0."' in text
    assert 'SET "DIR=C:\\praxiszeit"' not in text


def test_restore_bat_entpackt_nach_data_und_raeumt_reste_weg():
    text = _bat_text()
    assert 'SET "BACKUP_DUMP=%DIR%\\data\\.restore-praxiszeit.sql"' in text
    assert 'SET "REV_FILE=%DIR%\\data\\.restore-revision.txt"' in text
    # kein Klartext-Dump mehr in %TEMP% - nur noch das Wegraeumen alter Reste
    temp_refs = [line for line in _bat_lines()
                 if "%TEMP%" in line and not line.upper().startswith("REM")]
    assert temp_refs and all(line.startswith("del ") for line in temp_refs), temp_refs
    leftover = text.index('del "%BACKUP_DUMP%" 2>nul')
    assert leftover < text.index("Entpacke und pruefe Backup")


# --- Audit 2026-11-07 S3-02: uninstall.bat loescht nichts ohne geprueftes Backup

_UNINSTALL = _REPO / "installer" / "windows" / "uninstall.bat"


def _uninstall_text() -> str:
    return _UNINSTALL.read_bytes().decode("utf-8")


def test_uninstall_bat_hat_durchgehend_crlf():
    raw = _UNINSTALL.read_bytes()
    assert b"\n" not in raw.replace(b"\r\n", b""), "uninstall.bat braucht CRLF"


def test_uninstall_bat_prueft_exitcode_und_schlusszeile():
    text = _uninstall_text()
    dump = text.index('"%PG_DUMP%"')
    ok = text.index("\r\n:backup_ok\r\n")
    between = text[dump:ok]
    assert "if errorlevel 1 goto :backup_failed" in between
    assert 'findstr /c:"PostgreSQL database dump complete" "%BACKUP_FILE%"' in between
    assert "if exist \"%BACKUP_FILE%\" goto :backup_ok" not in text
    failed = text[text.index("\r\n:backup_failed\r\n"):ok]
    assert 'del "%BACKUP_FILE%"' in failed  # keine halbe Datei als "Backup"
    assert "2>nul" not in text[dump:text.index("\r\n", dump)]  # Grund wird angezeigt


def test_uninstall_bat_rettet_die_automatischen_sicherungen_vor_dem_loeschen():
    text = _uninstall_text()
    move = text.index('robocopy "%DIR%\\data\\backups" "%KEEP_DIR%" /E /MOVE')
    assert "if errorlevel 8 goto :keep_failed" in text[move:move + 200]
    assert move < text.index('echo rd /s /q "%DIR%"')
    keep_failed = text[text.index("\r\n:keep_failed\r\n"):text.index("\r\n:cancelled\r\n")]
    assert "exit /b 1" in keep_failed and "CLEANUP_BAT" not in keep_failed


def test_uninstall_bat_scram_und_leerzeichenpfad():
    text = _uninstall_text()
    assert 'SET "PGREQUIREAUTH=scram-sha-256"' in text
    assert text.index("PGREQUIREAUTH") < text.index('"%PG_DUMP%"')
    assert 'for /f "usebackq tokens=1,* delims==" %%a in ("%CREDS_FILE%") do (' in text
    assert "in (%CREDS_FILE%)" not in text


# --- Fix-Runde S3-03: Signatur der Sicherung + engere Pruefung ----------------

def test_restore_lehnt_unsignierte_sicherung_vor_jeder_aenderung_ab(srv, inst, caplog):
    cluster = FakeCluster()
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst, key=None), cluster)
    assert code == 1
    assert cluster.calls == []
    assert cluster.dbs["praxiszeit"] == _OLD
    assert "keine PraxisZeit-Signatur" in caplog.text and "--force-unverified" in caplog.text
    assert not list((inst / "data").glob(".restore-*"))


def test_restore_lehnt_fremd_signierte_sicherung_ab(srv, inst, caplog):
    cluster = FakeCluster()
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst, key="anderer-schluessel"), cluster)
    assert code == 1 and cluster.calls == []
    assert "passt nicht" in caplog.text


def test_restore_lehnt_veraenderte_sicherung_ab(srv, inst, caplog):
    path = inst / "data" / "backups" / "praxiszeit_20261017_120000.sql.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(_signed(_DUMP).replace("CREATE TABLE users ();", "CREATE TABLE boese ();"))
    cluster = FakeCluster()
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, path, cluster)
    assert code == 1 and cluster.calls == []
    assert "passt nicht" in caplog.text


def test_restore_ohne_secret_key_lehnt_ab(srv, inst, caplog, monkeypatch):
    monkeypatch.setattr(srv, "load_config", lambda: {})
    cluster = FakeCluster()
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst), cluster)
    assert code == 1 and cluster.calls == []
    assert "SECRET_KEY" in caplog.text


def test_restore_liest_den_schluessel_aus_secret_key_datei(srv, inst, monkeypatch):
    monkeypatch.setattr(srv, "load_config", lambda: {})
    (inst / "config").mkdir()
    (inst / "config" / ".secret-key").write_text(_KEY + "\n")
    cluster = FakeCluster()
    code, _ = _restore(srv, _dump(inst), cluster)
    assert code == 0
    assert _loaded(cluster.dbs["praxiszeit"]) == _DUMP_LOADED


def test_restore_force_unverified_spielt_unsignierte_sicherung_mit_warnung_ein(srv, inst, caplog):
    cluster = FakeCluster()
    with caplog.at_level(logging.WARNING, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst, key=None), cluster, force_unverified=True)
    assert code == 0
    assert "--force-unverified" in caplog.text
    assert _loaded(cluster.dbs["praxiszeit"]).startswith("--\n-- PostgreSQL database dump")


def test_force_unverified_prueft_trotzdem_auf_fremde_befehle(srv, inst, caplog):
    cluster = FakeCluster()
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst, _HEAD + "DO $$BEGIN NULL; END$$;\n" + _TAIL, key=None),
                           cluster, force_unverified=True)
    assert code == 1 and cluster.calls == []
    assert "pg_dump nie" in caplog.text


def test_parser_kennt_force_unverified(srv, monkeypatch):
    seen = {}
    monkeypatch.setattr(srv, "cmd_restore", lambda a: seen.setdefault("restore", a))
    monkeypatch.setattr(srv, "cmd_prepare_restore_dump", lambda a: seen.setdefault("prep", a))
    monkeypatch.setattr(sys, "argv", ["x", "restore", "/tmp/b.sql.gz", "--force-unverified"])
    srv.main()
    monkeypatch.setattr(sys, "argv", ["x", "prepare-restore-dump", "/tmp/b.sql"])
    srv.main()
    assert seen["restore"].force_unverified is True
    assert seen["prep"].force_unverified is False


def test_prepare_unterbefehl_exit_2_fuer_unsignierte_sicherung(srv, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(srv, "load_config", lambda: {"security": {"secret_key": _KEY}})
    p = tmp_path / "d.sql"
    p.write_text(_HEAD + _TAIL, encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        srv.cmd_prepare_restore_dump(argparse.Namespace(file=str(p), force_unverified=False))
    assert e.value.code == 2
    assert "--force-unverified" in capsys.readouterr().err
    assert p.read_text(encoding="utf-8") == _HEAD + _TAIL
    srv.cmd_prepare_restore_dump(argparse.Namespace(file=str(p), force_unverified=True))
    assert p.read_text(encoding="utf-8").startswith("\\restrict ")


def test_restore_bat_erklaert_force_unverified():
    text = _bat_text()
    assert 'if /i "%~2"=="--force-unverified" SET "PREP_FLAGS=--force-unverified"' in text
    prep = text.index('prepare-restore-dump %PREP_FLAGS% --restricted-load "%BACKUP_DUMP%"')
    after = text[prep:prep + 400]
    assert after.index('if "%PREP_RC%"=="2" goto :backup_unsigniert') < after.index(
        "goto :backup_abgelehnt")
    block = _bat_blocks()["backup_unsigniert"]
    assert 'del "%BACKUP_DUMP%" 2>nul' in block and "exit /b 1" in block
    assert any("--force-unverified" in line for line in block)


def test_native_backup_wird_signiert(srv, inst, monkeypatch):
    import io
    monkeypatch.setattr(srv, "BACKUP_DIR", inst / "data" / "backups")
    payload = (_DUMP).encode("utf-8")

    class _P:
        def __init__(self, *a, **k):
            self.stdout = io.BytesIO(payload)
            self.returncode = 0

        def wait(self):
            return 0

    monkeypatch.setattr(srv.subprocess, "Popen", _P)
    monkeypatch.setattr(srv, "pg_cmd", lambda name: Path("/x") / name)
    path = srv.create_backup({"security": {"secret_key": _KEY}})
    with gzip.open(path, "rb") as fh:
        assert srv.verify_backup_mac(fh, _KEY) == "ok"
    with gzip.open(path, "rb") as fh:
        assert fh.read().startswith(payload)
    # ... und restore nimmt sie ohne --force-unverified
    cluster = FakeCluster()
    code, _ = _restore(srv, path, cluster)
    assert code == 0
    assert _loaded(cluster.dbs["praxiszeit"]) == _DUMP_LOADED


_DANGEROUS = [
    # (a) COPY-Zeile mit weiteren Anweisungen dahinter: kein Datenmodus.
    "COPY t (a) FROM stdin; CREATE ROLE evil SUPERUSER; COPY u FROM stdin;\n",
    "COPY public.t (a) FROM stdin;x\n\\.\n",
    "COPY t FROM '/etc/passwd';\n",
    # (b)/(c) DO-Block mit dynamischem SQL
    "DO $$BEGIN EXECUTE 'COPY (SELECT 1) TO PROGRAM ''id > /tmp/pwn'''; END$$;\n",
    "DO $x$BEGIN EXECUTE 'ALTER ROLE praxiszeit_app BYPASSRLS'; END$x$;\n",
    "do\n$$ begin null; end $$;\n",
    "CALL boese();\n",
    # (d) Server-Dateien / Large Objects
    "SELECT lo_export(16384, '/tmp/x');\n",
    "SELECT pg_catalog.lo_import('/etc/shadow');\n",
    "CREATE TABLE t (a text CHECK (pg_read_file('/etc/passwd') IS NOT NULL));\n",
    "CREATE TABLE t (a text DEFAULT \"lo_export\"(1, '/tmp/x'));\n",
    "CREATE INDEX i ON t ((query_to_xml('select 1', true, true, '')));\n",
    # standard_conforming_strings / Sitzung
    "SET standard_conforming_strings = off;\n",
    "SET standard_conforming_strings TO 'off';\n",
    "SELECT pg_catalog.set_config('standard_conforming_strings', 'off', false);\n",
    "SET client_encoding = 'SJIS';\n",
    "SET LOCAL standard_conforming_strings = off;\n",
    "SET ROLE praxiszeit;\n",
    "SET SESSION AUTHORIZATION praxiszeit;\n",
    "SET session_preload_libraries = 'x';\n",
    "RESET ALL;\n",
    "SELECT 1;\n",
    # Rollen / Cluster
    "GRANT praxiszeit TO praxiszeit_app;\n",
    "GRANT pg_execute_server_program TO praxiszeit_app;\n",
    "GRANT \"x ON y\" TO praxiszeit_app;\n",
    "ALTER DATABASE praxiszeit SET search_path = evil;\n",
    "CREATE TABLESPACE x LOCATION '/tmp';\n",
    "CREATE SERVER s FOREIGN DATA WRAPPER postgres_fdw;\n",
    "CREATE USER MAPPING FOR praxiszeit SERVER s;\n",
    "CREATE EXTENSION plpython3u;\n",
    "CREATE EXTENSION IF NOT EXISTS adminpack;\n",
    # Funktionen
    "CREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS $$BEGIN EXECUTE 'x'; END$$;\n",
    "CREATE FUNCTION f() RETURNS void LANGUAGE sql AS 'ALTER ROLE praxiszeit_app SUPERUSER';\n",
    "CREATE FUNCTION f() RETURNS void LANGUAGE plpython3u AS $$import os$$;\n",
    "CREATE OR REPLACE FUNCTION f() RETURNS int LANGUAGE plpgsql AS "
    "$_$BEGIN PERFORM lo_export(1,'/x'); RETURN 1; END$_$;\n",
]


@pytest.mark.parametrize("body", _DANGEROUS)
def test_dump_mit_gefaehrlicher_anweisung_wird_abgelehnt(srv, tmp_path, body):
    with pytest.raises(srv.RestoreError, match="pg_dump nie|psql-Befehl|gehoert nicht"):
        _check(srv, tmp_path, body)


@pytest.mark.parametrize("body", [
    "COPY public.\"order\" (id, \"from\", \"a;b\") FROM stdin;\n1\t2\t3\n\\.\n",
    "COPY public.t FROM stdin;\n\\.\n",
    "SET search_path = public, pg_catalog;\n",
    "SET default_tablespace = '';\n",
    "SET client_encoding = 'UTF8';\n",
    "SELECT pg_catalog.set_config('search_path', '', false);\n",
    "SELECT pg_catalog.setval('public.t_id_seq', 42, true);\n",
    "CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;\n",
    "GRANT SELECT ON TABLE public.t TO praxiszeit_app;\n",
    "REVOKE ALL ON SCHEMA public FROM PUBLIC;\n",
    "CREATE FUNCTION public.f() RETURNS text LANGUAGE plpgsql AS $$BEGIN RETURN 'x'; END$$;\n",
    # Final-Review (S3-03-Rest): INSERT ist nicht mehr dabei - alle Sicherungswege
    # (backup, uninstall.bat, install.sh, Docker) rufen pg_dump ohne --inserts
    # auf, Daten kommen nur als COPY.
    "CREATE TABLE \"x ON y\" (a int);\n",
])
def test_dump_mit_ueblichen_anweisungen_geht_durch(srv, tmp_path, body):
    _check(srv, tmp_path, body)  # wirft nicht


def test_dump_endet_mitten_in_einer_anweisung(srv, tmp_path):
    p = tmp_path / "d.sql"
    p.write_text(_HEAD + "COMMENT ON TABLE t IS 'offen\n", encoding="utf-8")
    with pytest.raises(srv.RestoreError, match="mitten in einer Anweisung"):
        srv.validate_restore_dump(p)


# --- Audit 2026-11-07, Runde 3: Umgehungen des Validators auf --force-unverified ---
#
# Jeder Eintrag kam vor dieser Runde durch validate_restore_dump. Die Liste
# bleibt Verteidigung in der Tiefe; die eigentliche Grenze ist das Einspielen
# unverifizierter Sicherungen als Rolle OHNE Superuser-Rechte (unten).

_BYPASSES_ROUND3 = [
    # (1) Unicode-Bezeichner/-Zeichenketten verstecken Katalognamen.
    'ALTER TABLE pg_catalog.U&"pg\\005fauthid" OWNER TO praxiszeit_app;\n',
    "CREATE TABLE public.t (a text DEFAULT u&'\\0041');\n",
    # (2) pg_*-Name mit Klammer dahinter (Spaltenliste oder Aufruf) galt als
    #     erlaubter Funktionsaufruf; CREATE RULE ganz.
    "CREATE RULE r AS ON INSERT TO public.t DO ALSO INSERT INTO pg_catalog.pg_auth_members "
    "(roleid, member, grantor) VALUES (10, 16384, 10);\n",
    "CREATE RULE r AS ON SELECT TO public.t DO INSTEAD SELECT 1;\n",
    "CREATE TABLE public.t (a text DEFAULT pg_create_restore_point('x'));\n",
    "CREATE INDEX i ON public.t ((pg_catalog.binary_upgrade_set_next_pg_type_oid(1)));\n",
    # (3) E-Zeichenkette mit Backslash im Funktionsrumpf: p\x67 ist pg.
    "CREATE FUNCTION public.f() RETURNS void LANGUAGE sql AS "
    "E'UPDATE p\\x67_authid SET rolsuper = true';\n",
    "CREATE FUNCTION public.f() RETURNS text LANGUAGE plpgsql AS "
    "$$BEGIN RETURN E'a\\nb'; END$$;\n",
    # (4) Verschachtelte Anweisungen im Rumpf (innere Literale prueft niemand).
    "CREATE FUNCTION public.f() RETURNS void LANGUAGE plpgsql AS $$BEGIN "
    "CREATE FUNCTION public.g() RETURNS void LANGUAGE sql AS 'UPDATE /**/ pg_authid SET rolsuper = true'; "
    "END$$;\n",
    "CREATE FUNCTION public.f() RETURNS void LANGUAGE plpgsql AS $$BEGIN "
    "CREATE OR REPLACE FUNCTION public.g() RETURNS void LANGUAGE sql AS 'SELECT 1'; END$$;\n",
    "CREATE FUNCTION public.f() RETURNS void LANGUAGE plpgsql AS $$BEGIN "
    "ALTER FUNCTION public.g() SECURITY DEFINER; END$$;\n",
    "CREATE FUNCTION public.f() RETURNS void LANGUAGE plpgsql AS $$BEGIN "
    "CREATE TRIGGER t AFTER INSERT ON public.t FOR EACH ROW EXECUTE FUNCTION public.g(); END$$;\n",
    "CREATE FUNCTION public.f() RETURNS void LANGUAGE plpgsql AS $$BEGIN "
    "CREATE RULE r AS ON INSERT TO public.t DO ALSO NOTHING; END$$;\n",
    "CREATE FUNCTION public.f() RETURNS void LANGUAGE plpgsql AS $$BEGIN "
    "DO LANGUAGE plpgsql 'BEGIN NULL; END'; END$$;\n",
    # Weitere Funde dieser Runde: Kommentar bzw. Literal klebte Woerter
    # zusammen (ALTER/**/ROLE las sich als ALTERROLE) ...
    "ALTER/**/ROLE praxiszeit_app SUPERUSER;\n",
    "CREATE FUNCTION public.system(cstring) RETURNS int "
    "AS'/lib/x86_64-linux-gnu/libc.so.6'LANGUAGE c STRICT;\n",
    # ... die Sprache als Zeichenkette oder direkt in Anfuehrungszeichen ...
    "CREATE FUNCTION public.system(cstring) RETURNS int "
    "AS '/lib/x86_64-linux-gnu/libc.so.6', 'system' STRICT LANGUAGE 'c';\n",
    "CREATE FUNCTION public.system(cstring) RETURNS int "
    "AS '/lib/x86_64-linux-gnu/libc.so.6', 'system' LANGUAGE\"c\" STRICT;\n",
    # ... eine Dollar-Quote mit Nicht-ASCII-Marke (psql kennt sie, der Lexer
    # nicht) versteckte die Anweisung dazwischen in einer Schein-Zeichenkette ...
    "COMMENT ON TABLE public.t IS $\u00e4$'$\u00e4$; ALTER ROLE praxiszeit_app SUPERUSER; "
    "COMMENT ON TABLE public.t IS $\u00e4$'$\u00e4$;\n",
    # ... und BEGIN ATOMIC: psql liest den Rumpf als EINE Anweisung, der Lexer
    # trennte an jedem Semikolon.
    "CREATE FUNCTION public.f() RETURNS int LANGUAGE sql BEGIN ATOMIC "
    "INSERT INTO public.t VALUES (1); END;\n",
]


@pytest.mark.parametrize("body", _BYPASSES_ROUND3)
def test_runde3_umgehung_wird_abgelehnt(srv, tmp_path, body):
    with pytest.raises(srv.RestoreError, match="pg_dump nie"):
        _check(srv, tmp_path, body)


def test_funktionsrumpf_mit_on_conflict_do_nothing_geht_durch(srv, tmp_path):
    """DO ist im Rumpf nur als eigener Block verboten, nicht in ON CONFLICT."""
    _check(srv, tmp_path,
           "CREATE FUNCTION public.f() RETURNS void LANGUAGE plpgsql AS $$BEGIN "
           "INSERT INTO public.t VALUES (1) ON CONFLICT (id) DO NOTHING; END$$;\n")


_FIXTURE_DUMP = Path(__file__).resolve().parent / "fixtures" / "restore" / "pg_dump_076_schema.sql"


def test_echter_pg_dump_der_aktuellen_datenbank_geht_durch(srv, tmp_path):
    """Gegenprobe: echte Ausgabe von pg_dump 18.6 einer PraxisZeit-Datenbank auf
    Stand 076 (Schema samt RLS-Policies, Grants, den Protokollfunktionen und
    -Triggern aus Migration 076, alembic_version; ohne Personendaten)."""
    text = _FIXTURE_DUMP.read_text(encoding="utf-8")
    assert "\\restrict " in text and "pz_audit_guard" in text and "076_audit_chain" in text
    p = tmp_path / "d.sql"
    p.write_text(text, encoding="utf-8")
    srv.validate_restore_dump(p)  # wirft nicht


# --- Grenze: unverifizierte Sicherung als Rolle ohne Superuser-Rechte laden ---

def test_prepare_laesst_eigentuemer_nur_beim_eingeschraenkten_laden_weg(srv, tmp_path):
    """Die Ladrolle kann ``OWNER TO praxiszeit`` nicht ausfuehren; die Objekte
    gehoeren ihr und werden danach per REASSIGN OWNED uebertragen."""
    text = _FIXTURE_DUMP.read_text(encoding="utf-8")
    p = tmp_path / "d.sql"
    p.write_text(text, encoding="utf-8")
    assert srv.prepare_restore_dump(p, secret_key=_KEY, force_unverified=True,
                                    restricted_load=True) is False
    out = p.read_text(encoding="utf-8")
    assert " OWNER TO " not in out
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE" not in out
    assert "CREATE FUNCTION public.pz_audit_guard()" in out and "076_audit_chain" in out
    # Sonst bleibt alles gleich (nur die eigenen restrict-Zeilen sind ersetzt).
    kept = [line for line in text.splitlines()
            if " OWNER TO " not in line and not line.startswith(("\\restrict", "\\unrestrict",
                                                                 "ALTER DEFAULT PRIVILEGES FOR"))]
    assert out.splitlines()[1:] == kept
    # Signiert: unveraendert, verifiziert.
    p2 = tmp_path / "e.sql"
    p2.write_text(_signed(_HEAD + "ALTER TABLE public.t OWNER TO praxiszeit;\n" + _TAIL),
                  encoding="utf-8")
    assert srv.prepare_restore_dump(p2, secret_key=_KEY, restricted_load=True) is True
    assert "ALTER TABLE public.t OWNER TO praxiszeit;" in p2.read_text(encoding="utf-8")


def test_eigentuemerzeile_mit_zweiter_anweisung_bleibt_stehen(srv, tmp_path):
    p = tmp_path / "d.sql"
    body = "ALTER TABLE public.t OWNER TO praxiszeit; CREATE TABLE public.u ();\n"
    p.write_text(_HEAD + body + _TAIL, encoding="utf-8")
    srv.prepare_restore_dump(p, secret_key=_KEY, force_unverified=True, restricted_load=True)
    assert body in p.read_text(encoding="utf-8")


def test_unverifizierte_sicherung_wird_als_eingeschraenkte_rolle_geladen(srv, inst):
    cluster = FakeCluster()
    code, _ = _restore(srv, _dump(inst, _HEAD + "ALTER TABLE public.t OWNER TO praxiszeit;\n"
                                  + _TAIL, key=None), cluster, force_unverified=True)
    assert code == 0
    load = next(c for c in cluster.calls if "-f" in c and c[c.index("-f") + 1] not in ("-",)
                and not c[-1].endswith("init-db-user.sql"))
    assert load[load.index("-U") + 1] == srv.RESTORE_LOAD_ROLE
    load_env = cluster.envs[cluster.calls.index(load)]
    assert load_env["PGPASSWORD"] != "su-pw" and len(load_env["PGPASSWORD"]) >= 32
    # Passwort nie in einer Befehlszeile (Prozessliste), nur ueber stdin.
    assert all(load_env["PGPASSWORD"] not in arg for c in cluster.calls for arg in c)
    assert cluster.role_sql and "NOSUPERUSER" in cluster.role_sql[0]
    assert "NOCREATEROLE" in cluster.role_sql[0] and "NOBYPASSRLS" in cluster.role_sql[0]
    assert cluster.events == [
        "drop:praxiszeit_restore",
        "droprole:praxiszeit_restore_load",
        "createrole:praxiszeit_restore_load",
        "create:praxiszeit_restore",
        "grantload:praxiszeit_restore",
        "load:praxiszeit_restore",
        "revision:praxiszeit_restore",
        "routines:praxiszeit_restore",
        "aclreset:praxiszeit_restore",
        "reassign:praxiszeit_restore",
        "droprole:praxiszeit_restore_load",
        "drop:praxiszeit",
        "rename:praxiszeit_restore->praxiszeit",
        "grants:praxiszeit",
    ]
    create = next(c for c in cluster.calls if any("CREATE DATABASE" in a for a in c))
    # Review-Runde 6: nie der Ladrolle - Superuser, template0, nur CREATE im Schema
    assert any('OWNER "praxiszeit" TEMPLATE template0' in a for a in create)
    assert not any(srv.RESTORE_LOAD_ROLE in a for a in create)
    grant = next(c for c in cluster.calls if any(a.startswith("GRANT CREATE ON SCHEMA") for a in c))
    assert grant[grant.index("-d") + 1] == "praxiszeit_restore"
    assert "OWNER TO" not in cluster.dbs["praxiszeit"]


def test_signierte_sicherung_wird_weiter_als_superuser_geladen(srv, inst):
    cluster = FakeCluster()
    code, _ = _restore(srv, _dump(inst), cluster)
    assert code == 0
    load = next(c for c in cluster.calls if "-f" in c and not c[-1].endswith("init-db-user.sql"))
    assert load[load.index("-U") + 1] == "praxiszeit"
    assert cluster.role_sql == []


def test_ladrolle_wird_auch_nach_fehler_entfernt(srv, inst, caplog):
    cluster = FakeCluster(fail_load=True)
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst, key=None), cluster, force_unverified=True)
    assert code == 1
    assert cluster.dbs["praxiszeit"] == _OLD
    after_load = cluster.events[cluster.events.index("load:praxiszeit_restore"):]
    assert "droprole:praxiszeit_restore_load" in after_load
    assert cluster.roles == set()


# --- Review-Runde 4: Funktionen/Trigger einer unverifizierten Sicherung -------
# Nach REASSIGN OWNED gehoeren alle Objekte dem Superuser - eine Funktion, die
# die Pruefliste uebersieht, liefe danach als Trigger oder SECURITY DEFINER mit
# Superuser-Rechten. Deshalb muessen Funktionen und Trigger genau denen der
# Migrationen bis zum Datenbankstand der Sicherung entsprechen.

_VERSIONS = _REPO / "backend" / "alembic" / "versions"


def _fixture_routines(srv) -> tuple[dict, dict]:
    text = _FIXTURE_DUMP.read_text(encoding="utf-8")
    functions = {}
    # pg_dump waehlt $_$, wenn der Rumpf ein $ enthaelt
    for m in re.finditer(r"^CREATE FUNCTION public\.(\w+)\([^\n]*\n(.*?)AS (\$\w*\$)(.*?)\3;$",
                         text, re.S | re.M):
        functions[m.group(1)] = ("SECURITY DEFINER" in m.group(2), m.group(4))
    # pg_dump schreibt Trigger in der Form von pg_get_triggerdef
    triggers = {}
    for m in re.finditer(r"^CREATE TRIGGER .*;$", text, re.M):
        name, table, norm = srv.normalize_trigger_def(m.group(0))
        triggers[(name, table)] = norm
    return functions, triggers


def test_erwartete_funktionen_entsprechen_einem_echten_pg_dump(srv):
    """Was aus dem Quelltext der Migrationen gelesen wird, ist Zeichen fuer
    Zeichen das, was PostgreSQL speichert und pg_dump schreibt (Rumpf,
    SECURITY DEFINER, Trigger samt Definition) - geprueft am echten pg_dump
    18.6 auf Stand 076."""
    functions, triggers = srv.expected_db_routines(_VERSIONS, "076_audit_chain")
    fx_functions, fx_triggers = _fixture_routines(srv)
    assert set(functions) == set(fx_functions) and "pz_audit_tombstoned" in functions
    # Review-Runde 7: keine aufrufbare Vergabefunktion mehr, nur der Trigger
    assert "pz_audit_claim" in functions and "pz_audit_claim_id" not in functions
    for name, (lang, secdef, _config, src) in functions.items():
        assert (secdef, src) == fx_functions[name], name
        assert lang in ("sql", "plpgsql"), name
    assert triggers == fx_triggers and len(triggers) == 4
    # vor 076 legt keine Migration Funktionen oder Trigger an
    assert srv.expected_db_routines(_VERSIONS, "075_contract_history") == ({}, {})


def test_erwarteter_zeilenschutz_entspricht_einem_echten_pg_dump(srv):
    """ENABLE/FORCE ROW LEVEL SECURITY und die Policy-Namen, die aus den
    Migrationen (Schleifen ueber Tabellenlisten, f-Strings, Konstanten)
    gelesen werden, sind genau die des echten pg_dump auf Stand 076."""
    rls = srv.expected_db_rls(_VERSIONS, "076_audit_chain")
    text = _FIXTURE_DUMP.read_text(encoding="utf-8")
    enabled = set(re.findall(r"^ALTER TABLE public\.(\w+) ENABLE ROW LEVEL SECURITY;$", text, re.M))
    forced = set(re.findall(r"^ALTER TABLE (?:ONLY )?public\.(\w+) FORCE ROW LEVEL SECURITY;$",
                            text, re.M))
    policies = set(re.findall(r"^CREATE POLICY (\w+) ON public\.(\w+) ", text, re.M))
    assert {t for t, v in rls.items() if v["enable"]} == enabled
    assert {t for t, v in rls.items() if v["force"]} == forced
    assert {(p, t) for t, v in rls.items() for p in v["policies"]} == policies
    assert "audit_log_ids" in enabled and "audit_log_ids" not in forced
    assert len(enabled) >= 29


def _found(functions: dict, triggers: dict, **extra) -> dict:
    return {
        "functions": [{"schema": "public", "name": n, "lang": lang, "secdef": secdef,
                       "config": config, "src": src}
                      for n, (lang, secdef, config, src) in functions.items()],
        "triggers": [{"schema": "public", "name": t, "table": tbl, "function": "x", "enabled": "O",
                      "def": _pg_triggerdef(t, norm)}
                     for (t, tbl), norm in triggers.items()],
        "other": [],
        "extensions": [{"name": "plpgsql", "owner_super": True, "members": [
            "function plpgsql_call_handler()", "function plpgsql_inline_handler(internal)",
            "function plpgsql_validator(oid)", "language plpgsql"]}],
        **extra,
    }


def _pg_triggerdef(name: str, norm: str) -> str:
    """Normalform zurueck in die Form von pg_get_triggerdef."""
    rest = norm.split(" ", 1)[1]  # ohne "TRIGGER"
    timing, rest = rest.split(" ", 1)
    return f"CREATE TRIGGER {name} {timing} {rest}".replace(" ON ", " ON public.", 1)


def test_funktionsabgleich_findet_jede_abweichung(srv):
    functions, triggers = srv.expected_db_routines(_VERSIONS, "076_audit_chain")
    assert srv.check_restored_routines(_found(functions, triggers), functions, triggers) == []

    def problems(mutate):
        found = _found(functions, triggers)
        mutate(found)
        return srv.check_restored_routines(found, functions, triggers)

    def tamper(found):
        f = next(f for f in found["functions"] if f["name"] == "pz_audit_guard")
        f["src"] = f["src"].replace("RETURN NEW;", "PERFORM 1; RETURN NEW;", 1)
    assert problems(tamper) == ["Funktion public.pz_audit_guard (Inhalt weicht von der Migration ab)"]

    def extra(found):
        found["functions"].append({"schema": "public", "name": "boese", "lang": "plpgsql",
                                   "secdef": True, "config": "", "src": "BEGIN END"})
    assert problems(extra) == ["Funktion public.boese (legt keine Migration an)"]

    def secdef(found):
        f = next(f for f in found["functions"] if f["name"] == "pz_audit_head_guard")
        f["secdef"] = True
    assert "SECURITY DEFINER" in problems(secdef)[0]

    def other_schema(found):
        found["functions"].append({"schema": "extra", "name": "pz_audit_guard", "lang": "plpgsql",
                                   "secdef": False, "config": "", "src": "x"})
    assert problems(other_schema) == ["Funktion extra.pz_audit_guard (unerwartet)"]

    def missing(found):
        found["functions"] = [f for f in found["functions"] if f["name"] != "pz_audit_tombstoned"]
    assert problems(missing) == ["Funktion public.pz_audit_tombstoned fehlt"]

    def disabled(found):
        found["triggers"][0]["enabled"] = "D"
    assert "abgeschaltet" in problems(disabled)[0]

    def foreign_trigger(found):
        found["triggers"].append({"schema": "public", "name": "t", "table": "users",
                                  "function": "pz_audit_guard", "enabled": "O",
                                  "def": "CREATE TRIGGER t BEFORE INSERT ON public.users FOR EACH "
                                         "ROW EXECUTE FUNCTION pz_audit_guard()"})
    assert problems(foreign_trigger) == ["Trigger t auf public.users (unerwartet)"]

    def view(found):
        found["other"] = ["Sicht public.v"]
    assert problems(view) == ["Sicht public.v"]


_GUARD_DEF = ("CREATE TRIGGER pz_audit_guard_write BEFORE INSERT OR DELETE OR UPDATE ON "
              "public.time_entry_audit_logs FOR EACH ROW EXECUTE FUNCTION pz_audit_guard()")


@pytest.mark.parametrize("tampered", [
    # Runde 6: gleicher Name, Tabelle, Funktion - aber wirkungslos gemacht
    _GUARD_DEF.replace("BEFORE", "AFTER"),                       # zu spaet: Zeile schon geschrieben
    _GUARD_DEF.replace("INSERT OR DELETE OR UPDATE", "INSERT"),  # UPDATE/DELETE unbewacht
    _GUARD_DEF.replace("FOR EACH ROW", "FOR EACH STATEMENT"),    # NEW/OLD fehlen, nie RAISE
    _GUARD_DEF.replace("UPDATE ON", "UPDATE OF note ON"),        # nur eine Spalte bewacht
    _GUARD_DEF.replace(" EXECUTE", " WHEN ((pg_trigger_depth() > 5)) EXECUTE"),  # nie
    _GUARD_DEF.replace("CREATE TRIGGER", "CREATE CONSTRAINT TRIGGER").replace(
        "BEFORE", "AFTER").replace(" FOR EACH", " DEFERRABLE INITIALLY DEFERRED FOR EACH"),
])
def test_trigger_mit_veraenderter_definition_wird_erkannt(srv, tampered):
    functions, triggers = srv.expected_db_routines(_VERSIONS, "076_audit_chain")
    found = _found(functions, triggers)
    guard = next(t for t in found["triggers"] if t["name"] == "pz_audit_guard_write")
    assert srv.normalize_trigger_def(guard["def"]) == srv.normalize_trigger_def(_GUARD_DEF)
    guard["def"] = tampered
    assert srv.check_restored_routines(found, functions, triggers) == [
        "Trigger pz_audit_guard_write auf time_entry_audit_logs (Definition weicht von der "
        "Migration ab)"]


def test_trigger_normalform_ist_unabhaengig_von_schreibweise(srv):
    a = srv.normalize_trigger_def(
        "CREATE TRIGGER t BEFORE INSERT OR UPDATE OR DELETE ON x FOR ROW EXECUTE PROCEDURE f()")
    b = srv.normalize_trigger_def(
        'CREATE TRIGGER t BEFORE INSERT OR DELETE OR UPDATE ON public."x" FOR EACH ROW '
        "EXECUTE FUNCTION public.f()")
    assert a == b
    assert srv.normalize_trigger_def("CREATE TABLE t (a int)") is None


@pytest.mark.parametrize("ext, problem", [
    # Runde 6: Funktionen einer Erweiterung (pg_depend 'e') nahm der Abgleich
    # frueher pauschal aus - ALTER EXTENSION ... ADD FUNCTION versteckte so
    # eine eigene Funktion, REASSIGN OWNED gab sie dem Superuser.
    ({"name": "pgcrypto", "owner_super": True, "members": []},
     "Erweiterung pgcrypto (legt keine Migration an)"),
    ({"name": "plpgsql", "owner_super": False, "members": [
        "function plpgsql_call_handler()", "function plpgsql_inline_handler(internal)",
        "function plpgsql_validator(oid)", "language plpgsql"]},
     "Erweiterung plpgsql gehoert nicht dem Datenbank-Superuser"),
    ({"name": "plpgsql", "owner_super": True, "members": [
        "function plpgsql_call_handler()", "function plpgsql_inline_handler(internal)",
        "function plpgsql_validator(oid)", "language plpgsql", "function boese()"]},
     "Erweiterung plpgsql (Bestandteile weichen vom Standard ab)"),
])
def test_erweiterungen_werden_gegen_den_standard_geprueft(srv, ext, problem):
    functions, triggers = srv.expected_db_routines(_VERSIONS, "076_audit_chain")
    found = _found(functions, triggers, extensions=[ext])
    assert srv.check_restored_routines(found, functions, triggers) == [problem]


def test_erweiterungsfunktion_ausserhalb_pg_catalog_wird_geprueft(srv):
    """Der Katalog nimmt Erweiterungs-Funktionen nicht mehr aus (kein deptype-
    'e'-Filter): eine per ALTER EXTENSION ADD versteckte Funktion in public
    taucht im Abgleich auf."""
    assert "deptype = 'e')), '[]'" not in srv._ROUTINE_CATALOG_SQL
    assert "AND NOT EXISTS (SELECT 1 FROM pg_depend" not in srv._ROUTINE_CATALOG_SQL


@pytest.mark.parametrize("body", [
    "ALTER EXTENSION plpgsql ADD FUNCTION public.boese();\n",
    "ALTER EXTENSION pg_trgm UPDATE;\n",
])
def test_alter_extension_wird_immer_abgelehnt(srv, tmp_path, body):
    with pytest.raises(srv.RestoreError, match="ALTER EXTENSION"):
        _check(srv, tmp_path, body)


@pytest.mark.parametrize("body", [
    "CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;\n",
    "CREATE EXTENSION pg_trgm;\n",
    "CREATE EXTENSION plpgsql;\n",
    "COMMENT ON EXTENSION plpgsql IS 'x';\n",
    "DROP EXTENSION IF EXISTS plpgsql;\n",
])
def test_unverifizierte_sicherung_bringt_keine_erweiterung_mit(srv, tmp_path, body):
    p = tmp_path / "d.sql"
    p.write_text(_HEAD + body + _TAIL, encoding="utf-8")
    with pytest.raises(srv.RestoreError, match="Erweiterung in einer unverifizierten"):
        srv.prepare_restore_dump(p, secret_key=_KEY, force_unverified=True, restricted_load=True)


def test_unverifizierte_sicherung_darf_plpgsql_noop_und_signierte_erweiterungen(srv, tmp_path):
    p = tmp_path / "d.sql"
    p.write_text(_HEAD + "CREATE EXTENSION IF NOT EXISTS plpgsql WITH SCHEMA pg_catalog;\n"
                 + _TAIL, encoding="utf-8")
    assert srv.prepare_restore_dump(p, secret_key=_KEY, force_unverified=True,
                                    restricted_load=True) is False
    p2 = tmp_path / "e.sql"
    p2.write_text(_signed(_HEAD + "CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;\n"
                          + _TAIL), encoding="utf-8")
    assert srv.prepare_restore_dump(p2, secret_key=_KEY, restricted_load=True) is True


# --- Review-Runde 6: Zeilenschutz (RLS) einer unverifizierten Sicherung ------

_POL = {"name": "tenant_isolation", "cmd": "*", "permissive": True, "roles": ["public"],
        "qual": "((current_setting('app.is_superadmin'::text, true) = 'true'::text) OR "
                "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid))",
        "check": None}


def _rls_case(srv, **table):
    rls = srv.expected_db_rls(_VERSIONS, "076_audit_chain")
    tables = [{"name": "absences", "schema": "public", "rls": True, "force": True, **table}]
    script, order = srv.rls_deparse_sql(rls, {"absences"})
    assert order == ["absences"] and "LIKE public.\"absences\"" in script
    assert "CREATE POLICY \"tenant_isolation\" ON pg_temp.pz_rls_0" in script
    assert script.startswith("BEGIN;") and script.rstrip().endswith("ROLLBACK;")
    return rls, tables, order


def test_rls_abgleich_findet_jede_abweichung(srv):
    rls, tables, order = _rls_case(srv)
    same = {"expected": [{**_POL, "table": "pz_rls_0"}], "found": [{**_POL, "table": "absences"}]}
    assert srv.check_restored_rls(tables, rls, same, order) == []

    off = [{**tables[0], "rls": False}]
    assert srv.check_restored_rls(off, rls, same, order) == [
        "Tabelle public.absences: Zeilenschutz (RLS) ist abgeschaltet"]
    no_force = [{**tables[0], "force": False}]
    assert srv.check_restored_rls(no_force, rls, same, order) == [
        "Tabelle public.absences: FORCE ROW LEVEL SECURITY fehlt"]
    mismatch = "Tabelle public.absences: Zeilenschutz-Regeln (Policies) weichen von den Migrationen ab"
    for found in (
        [{**_POL, "table": "absences", "qual": "true"}],                       # alles offen
        [{**_POL, "table": "absences"}, {**_POL, "table": "absences", "name": "x", "qual": "true"}],
        [{**_POL, "table": "absences", "cmd": "r"}],                           # nur SELECT bewacht
        [{**_POL, "table": "absences", "roles": ["praxiszeit"]}],              # App-Rolle frei
        [],                                                                    # Policy fehlt
    ):
        assert srv.check_restored_rls(tables, rls, {**same, "found": found}, order) == [mismatch]
    # fehlende Tabelle schwaecht nichts - kein Befund hier
    assert srv.check_restored_rls([], rls, None, []) == []


def test_unverifizierte_sicherung_mit_offener_policy_wird_nicht_uebernommen(srv, inst, caplog,
                                                                         monkeypatch):
    # echte Migrationen (Stand 076) statt der Stummel des Installationsordners
    monkeypatch.setattr(srv, "BACKEND_DIR", _REPO / "backend")
    cluster = FakeCluster(revision="076_audit_chain")
    functions, triggers = srv.expected_db_routines(_VERSIONS, "076_audit_chain")
    cluster.routines = _found(functions, triggers, tables=[
        {"name": "absences", "schema": "public", "rls": True, "force": True}])
    cluster.rls_deparsed = {"expected": [{**_POL, "table": "pz_rls_0"}],
                            "found": [{**_POL, "table": "absences", "qual": "true"}]}
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst, key=None), cluster, force_unverified=True)
    assert code == 1
    assert "public.absences: Zeilenschutz-Regeln" in caplog.text
    assert cluster.events.index("rls:praxiszeit_restore") > cluster.events.index(
        "routines:praxiszeit_restore")
    assert "reassign:praxiszeit_restore" not in cluster.events
    assert cluster.dbs["praxiszeit"] == _OLD
    # dieselbe Sicherung mit unveraenderter Policy geht durch
    ok = FakeCluster(revision="076_audit_chain")
    ok.routines = cluster.routines
    ok.rls_deparsed = {"expected": [{**_POL, "table": "pz_rls_0"}],
                       "found": [{**_POL, "table": "absences"}]}
    code, _ = _restore(srv, _dump(inst, key=None, name="praxiszeit_20261017_120001.sql.gz"),
                       ok, force_unverified=True)
    assert code == 0 and "rls:praxiszeit_restore" in ok.events


def test_unverifizierte_sicherung_mit_fremder_funktion_wird_nicht_uebernommen(srv, inst, caplog):
    cluster = FakeCluster()
    cluster.routines["functions"].append({"schema": "public", "name": "boese", "lang": "plpgsql",
                                          "secdef": True, "config": "", "src": "BEGIN END"})
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst, key=None), cluster, force_unverified=True)
    assert code == 1
    assert "public.boese" in caplog.text and "Superuser" in caplog.text
    assert cluster.dbs["praxiszeit"] == _OLD
    after = cluster.events[cluster.events.index("routines:praxiszeit_restore"):]
    # Zwischendatenbank weg, BEVOR die Ladrolle (und damit ihre Objekte) geht -
    # nie REASSIGN der abgelehnten Objekte an den Superuser.
    assert after[1] == "drop:praxiszeit_restore"
    assert "reassign:praxiszeit_restore" not in after
    assert "droprole:praxiszeit_restore_load" in after
    assert not any(e.startswith("rename:") for e in cluster.events)
    assert cluster.roles == set()


def test_signierte_sicherung_braucht_keinen_funktionsabgleich(srv, inst):
    cluster = FakeCluster()
    cluster.routines["functions"].append({"schema": "public", "name": "egal", "lang": "sql",
                                          "secdef": False, "config": "", "src": "SELECT 1"})
    code, _ = _restore(srv, _dump(inst), cluster)
    assert code == 0 and "routines:praxiszeit_restore" not in cluster.events


# --- Review-Runde 7: Rechte, Tabellen, Vererbung ------------------------------

def test_signierte_sicherung_behaelt_ihre_rechte(srv, inst):
    cluster = FakeCluster()
    code, _ = _restore(srv, _dump(inst), cluster)
    assert code == 0 and "aclreset:praxiszeit_restore" not in cluster.events


def test_unverifizierte_sicherung_verliert_jedes_fremde_recht_vor_der_uebergabe(srv, inst):
    """Ein ``GRANT TRUNCATE ... TO PUBLIC`` der Sicherung ginge durch die
    Pruefliste und ueberlebte REASSIGN/DROP OWNED. Die Rechte werden nach dem
    Abgleich und VOR der Uebergabe an den Superuser zurueckgesetzt,
    init-db-user.sql vergibt danach die der Anwendung neu."""
    body = "GRANT TRUNCATE ON TABLE public.time_entry_audit_logs TO PUBLIC;\n"
    path = inst / "x.sql"
    path.write_text(_HEAD + body + _TAIL, encoding="utf-8")
    srv.validate_restore_dump(path, strip_ownership=True)  # Pruefliste allein laesst es durch
    cluster = FakeCluster()
    code, _ = _restore(srv, _dump(inst, _HEAD + body + _TAIL, key=None), cluster,
                       force_unverified=True)
    assert code == 0
    ev = cluster.events
    assert ev.index("routines:praxiszeit_restore") < ev.index("aclreset:praxiszeit_restore") \
        < ev.index("reassign:praxiszeit_restore") < ev.index("grants:praxiszeit")
    reset = next(c for c in cluster.calls if any(a.startswith("DO $pz_acl$") for a in c))
    assert reset[reset.index("-d") + 1] == "praxiszeit_restore"
    assert reset[reset.index("-U") + 1] == "praxiszeit"  # Superuser, nicht die Ladrolle


def test_scheitert_das_ruecksetzen_der_rechte_bleibt_der_bestand(srv, inst, caplog):
    cluster = FakeCluster()
    cluster.fail_acl_reset = True
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst, key=None), cluster, force_unverified=True)
    assert code == 1
    assert "Rechte der eingespielten Sicherung" in caplog.text
    assert cluster.dbs["praxiszeit"] == _OLD
    assert "reassign:praxiszeit_restore" not in cluster.events
    assert not any(e.startswith("rename:") for e in cluster.events)


def test_rechte_ruecksetzung_erfasst_tabellen_spalten_sequenzen_und_funktionen(srv):
    sql = srv._RESTORE_ACL_RESET_SQL
    for needle in ("aclexplode(c.relacl)", "aclexplode(t.attacl)", "aclexplode(p.proacl)",
                   "a.grantee <> c.relowner", "a.grantee <> p.proowner", "'PUBLIC'",
                   "'SEQUENCE'", "CASCADE", "n.nspname = 'public'"):
        assert needle in sql, needle


def test_erwartete_tabellen_entsprechen_einem_echten_pg_dump(srv):
    text = _FIXTURE_DUMP.read_text(encoding="utf-8")
    dumped = set(re.findall(r"^CREATE TABLE public\.(\w+) ", text, re.M))
    tables = srv.expected_db_tables(_VERSIONS, "076_audit_chain")
    assert tables | {"alembic_version"} == dumped
    assert {"audit_log_ids", "audit_log_tombstones", "users"} <= tables
    assert "audit_log_ids" not in srv.expected_db_tables(_VERSIONS, "075_contract_history")


def test_tabellenabgleich_findet_fremde_tabellen_vererbung_und_partitionen(srv):
    expected = srv.expected_db_tables(_VERSIONS, "076_audit_chain")
    ok = {"tables": [{"schema": "public", "name": n, "kind": "r"}
                     for n in sorted(expected | {"alembic_version"})], "inherits": []}
    assert srv.check_restored_tables(ok, expected) == []
    # fehlende Tabellen schwaechen nichts
    assert srv.check_restored_tables({"tables": [], "inherits": []}, expected) == []
    bad = {"tables": ok["tables"] + [
        {"schema": "public", "name": "audit_shadow", "kind": "r"},
        {"schema": "public", "name": "users_part", "kind": "p"},
        {"schema": "public", "name": "remote", "kind": "f"},
    ], "inherits": [{"child": "table public.audit_shadow",
                     "parent": "table public.time_entry_audit_logs"}]}
    got = srv.check_restored_tables(bad, expected)
    assert "Tabelle public.audit_shadow (legt keine Migration an)" in got
    assert any(p.startswith("Tabelle public.users_part (partitionierte") for p in got)
    assert any(p.startswith("Tabelle public.remote (partitionierte") for p in got)
    assert ("Vererbung/Partition: table public.audit_shadow haengt an table "
            "public.time_entry_audit_logs (legt keine Migration an)") in got
    assert len(got) == 4


def test_unverifizierte_sicherung_mit_kindtabelle_wird_nicht_uebernommen(srv, inst, caplog,
                                                                     monkeypatch):
    """``CREATE TABLE audit_shadow () INHERITS (time_entry_audit_logs)`` -
    die Pruefliste laesst es durch, das Kind haette weder Trigger noch RLS."""
    body = ("CREATE TABLE public.audit_shadow () INHERITS (public.time_entry_audit_logs);\n")
    path = inst / "x.sql"
    path.write_text(_HEAD + body + _TAIL, encoding="utf-8")
    srv.validate_restore_dump(path, strip_ownership=True)
    monkeypatch.setattr(srv, "BACKEND_DIR", _REPO / "backend")
    cluster = FakeCluster(revision="076_audit_chain")
    functions, triggers = srv.expected_db_routines(_VERSIONS, "076_audit_chain")
    cluster.routines = _found(functions, triggers, tables=[
        {"name": "time_entry_audit_logs", "schema": "public", "rls": False, "force": False,
         "kind": "r"},
        {"name": "audit_shadow", "schema": "public", "rls": False, "force": False, "kind": "r"},
    ], inherits=[{"child": "table public.audit_shadow",
                  "parent": "table public.time_entry_audit_logs"}])
    cluster.rls_deparsed = {"expected": [], "found": []}
    with caplog.at_level(logging.ERROR, logger="praxiszeit"):
        code, _ = _restore(srv, _dump(inst, _HEAD + body + _TAIL, key=None), cluster,
                           force_unverified=True)
    assert code == 1
    assert "public.audit_shadow" in caplog.text and "Vererbung/Partition" in caplog.text
    assert "reassign:praxiszeit_restore" not in cluster.events
    assert cluster.dbs["praxiszeit"] == _OLD

