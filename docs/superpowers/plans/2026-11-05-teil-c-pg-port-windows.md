# Teil C — PostgreSQL-Port unter Windows: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Native Windows installations can run their own PostgreSQL on a configurable port (`[database] port`, default 5432). A foreign PostgreSQL on that port is detected and named; it is never mistaken for the own cluster.

**Architecture:** One port source `pg_port()` in `praxiszeit-server.py` feeds everything that reaches the cluster: `pg_isready`, `_database_url` (and through it alembic, uvicorn and the in-app backup), `pg_env` (`PGHOST`/`PGPORT` for every psql/pg_dump call) and the managed block of `postgresql.conf`. An ownership check bound to `PG_DATA` (`pg_ctl status -D` + port line of `postmaster.pid`) replaces the bare `pg_isready` trust on Windows. The batch files read the port through a new `print-db-port` subcommand, and the GUI installer writes it.

**Tech Stack:** Python 3.12/3.13 (server script, pytest via the backend image), Windows batch (CRLF, ASCII), PowerShell, .NET 10 + Avalonia + xunit/FluentAssertions (GUI installer), dockur/windows emulator (`tools/win-test`).

**Spec:** `docs/superpowers/specs/2026-11-02-tillwich-rechte-terminal-pgport-design.md`, section 4 (Teil C). Code facts: survey `wf_b8191694-335` from 2026-11-05 on master 45447bd8 (1.22.0); line numbers below are from that state.

## Global Constraints

- Default without a `[database] port` entry = 5432 = exactly today's behaviour (URL string, conf, commands). Existing installations need no action.
- Port applies on **Windows only**. Linux/macOS stay socket-only on 5432; a `port` entry there is ignored with one log warning (socket file name `.s.PGSQL.5432`, `pg_env` pops `PGPORT` there).
- Allowed port values: integers 1024–65535 (TOML int or numeric string).
- `[database] port` is read only by `praxiszeit-server.py`. Do **not** add it to `backend/app/config.py::_TOML_KEY_MAP` or to `_CONF_TO_ENV` (`praxiszeit-server.py:1265-1287`); the backend gets the port only through `DATABASE_URL`/`DATABASE_URL_MIGRATIONS`.
- Keep `pg_is_running()`, `pg_start()`, `pg_stop()` **zero-argument** (existing stubs `lambda: False` in `test_native_pg_lifecycle.py:233,566` and `test_native_restore.py:184-186` must keep working). They read the port internally.
- Never use `os.kill(pid, 0)` as a liveness probe on Windows (sends CTRL_C_EVENT). Use `pg_ctl status -D PG_DATA`.
- Exact user messages (German, fixed copy):
  - Foreign server: `Port {port} ist von einem anderen PostgreSQL belegt. In config\praxiszeit.conf unter [database] einen freien Port eintragen (z. B. 5433) und den Dienst neu starten.`
  - Invalid value: `Ungültiger Datenbank-Port in config\praxiszeit.conf ([database] port = {raw}): erlaubt sind ganze Zahlen von 1024 bis 65535.`
- Configuration errors (both messages) end the process with exit code `EXIT_CONFIG_ERROR = 78`. The Windows service (NSSM) is told not to restart on 78 (`AppExit 78 Exit`).
- **Deviations from spec 4.2 (decided while planning, from the code survey):** (a) the abort does not go through `should_give_up` (that counts only uvicorn restarts in the watchdog) but through `PgConfigError` → exit 78 + NSSM `AppExit 78 Exit`; (b) “PID lebt” is checked with `pg_ctl status -D`, not `os.kill`; (c) `uninstall.bat` (pre-uninstall `pg_dump` without `-p`) is added; (d) `--serverport` in `setup.bat` is cosmetic (EDB service is deleted right after install; the system-PG branch skips EDB) — the real fix is at service start.
- Batch files stay **CRLF**; `restore-backup.template.bat` stays pure **ASCII** (`test_native_restore.py:605` decodes as ascii). Every `"%PSQL%"`/`"%PYTHON%"` line in its main block is followed by `if errorlevel 1`; no new `"%PYTHON%"` line may contain the word `alembic`.
- New native test file must be added to `scripts/local-ci.sh` step 3 pytest list (`:171-174`); GitHub Actions picks it up automatically.
- Commit messages in English, Conventional Commits, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Branch from master: `feat/pg-port-windows`. master is PR-only.

**Native test command** (repo root of the worktree; used as `$NATIVE_TESTS` below):

```bash
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/work -w /work/backend -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp \
  -e SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') -e ADMIN_EMAIL=ci@example.invalid \
  -e ADMIN_PASSWORD=LocalCiDummy2025X -e APP_DB_USER=ci -e APP_DB_PASSWORD=ci -e ENVIRONMENT=development \
  -e CORS_ORIGINS=http://localhost -e DATABASE_URL=sqlite:////tmp/native.db praxiszeit-backend \
  python -m pytest tests/test_native_pg_port.py tests/test_native_pg_lifecycle.py tests/test_native_restore.py \
  tests/test_native_security_hardening.py -q --tb=short </dev/null
```

Inside `docker compose exec backend` these tests only skip (no repo mount) — never use that.

## Review Focus

1. **Update of an existing 1.22 Windows installation without a port entry** — must start, back up and restore exactly as before; `postgresql.conf` untouched. → Task 4 test `test_sync_is_noop_for_default_conf`, Task 3 test `test_own_cluster_on_default_port_is_running`, emulator scenario (a) in Task 7.
2. **Port changed in the conf while the PostgreSQL service is still running on the old port** — `port` needs a postmaster restart; without one `net start` is a no-op and startup hangs 60 s. Expect: rewrite, stop the service, start it on the new port. → Task 4 test `test_changed_port_stops_running_service_before_start`.
3. **Foreign PostgreSQL appears later (e.g. another program installs PG 18 on 5432 after PraxisZeit)** — the watchdog must not call `pg_start()` in a loop; expect the foreign-server message and exit 78. → Task 3 test `test_watchdog_exits_on_foreign_server`.
4. **Repair in the GUI installer rewrites the whole conf with field defaults** — a customised DB port falls back to 5432 (same class as HTTPS port today). Expect: if 5432 is foreign, the clear message from Task 3 instead of a silent mix-up; the Ports page warns that 5432 is busy. → Task 6 test `Validate_warns_when_db_port_is_busy` (view-model logic in Core helper) + Task 3 message tests. Prefilling from the existing conf is out of scope (note in CHANGELOG).
5. **restore-backup.bat after a conf edit, before the service ran once** — the cluster's `postgresql.conf` still has the old port while `print-db-port` returns the new one. Expect: restore applies the conf port first. → Task 5 makes the restore script call `praxiszeit-server.py sync-db-port` before `pg_ctl start`; test `test_restore_bat_syncs_port_before_cluster_start`.

---

### Task 1: One port source, config validation, CLI subcommands

**Files:**
- Modify: `praxiszeit-server.py` (new helpers near `get_config_value` :171; argparse in `main()` :2917-2968; dispatch `try/except` around `args.func(args)`)
- Modify: `installer/praxiszeit.conf.example:14-18`
- Create: `backend/tests/test_native_pg_port.py`
- Modify: `scripts/local-ci.sh:171-174`

**Interfaces:**
- Produces:
  - `DEFAULT_PG_PORT = 5432`, `EXIT_CONFIG_ERROR = 78`
  - `class PgConfigError(Exception)` — message is user copy, printed by `main()`
  - `class ForeignPostgresError(PgConfigError)` — defined here, raised from Task 3
  - `parse_pg_port(config: dict) -> int` — pure: missing → 5432; int/numeric str in 1024–65535 → int; else `PgConfigError(<invalid message>)`. Ignores `IS_WINDOWS`.
  - `pg_port() -> int` — `5432` if not `IS_WINDOWS` (log one warning when an entry exists); else `parse_pg_port(load_config())`.
  - CLI `print-db-port` → `cmd_print_db_port(args)`: prints `pg_port()` as the only stdout line.
  - `main()` catches `PgConfigError`: `logger.error(str(e))`, `sys.exit(EXIT_CONFIG_ERROR)`.

- [ ] **Step 1: Create branch** `git switch -c feat/pg-port-windows origin/master`.
- [ ] **Step 2: Write failing tests** in `backend/tests/test_native_pg_port.py`. Header pattern of `test_native_pg_lifecycle.py:29-44` (skipif when `../praxiszeit-server.py` is missing, module-scoped `srv` fixture, module name `praxiszeit_server_pgport`). Tests:

```python
class TestParsePgPort:
    def test_missing_entry_is_default(self, srv): assert srv.parse_pg_port({}) == 5432
    def test_int_entry(self, srv): assert srv.parse_pg_port({"database": {"port": 5433}}) == 5433
    def test_numeric_string_entry(self, srv): assert srv.parse_pg_port({"database": {"port": "5433"}}) == 5433
    @pytest.mark.parametrize("raw", [0, 80, 1023, 65536, "abc", "54.3", True, -1])
    def test_invalid_entry_raises_with_copy(self, srv, raw):
        with pytest.raises(srv.PgConfigError) as e: srv.parse_pg_port({"database": {"port": raw}})
        assert "erlaubt sind ganze Zahlen von 1024 bis 65535" in str(e.value)

class TestPgPortPlatform:
    def test_windows_reads_config(self, srv, monkeypatch):  # IS_WINDOWS True, load_config -> {"database":{"port":5433}} => 5433
    def test_unix_ignores_entry(self, srv, monkeypatch):    # IS_WINDOWS False, same config => 5432

class TestPrintDbPortCli:
    def test_prints_port_only(self, srv, monkeypatch, capsys):  # argv ["x","print-db-port"], Windows, port 5433 => capsys.out == "5433\n"
    def test_invalid_config_exits_78(self, srv, monkeypatch):    # port "abc" => SystemExit.code == 78
```

(`True` must be rejected: `bool` is an `int` subclass.)
- [ ] **Step 3: Run** `$NATIVE_TESTS` limited to `tests/test_native_pg_port.py` → FAIL (`AttributeError: parse_pg_port`).
- [ ] **Step 4: Implement** the Produces list in `praxiszeit-server.py`. Register `print-db-port` like the other subparsers (`.set_defaults(func=cmd_print_db_port)`); extend the existing dispatch `try` with `except PgConfigError`.
- [ ] **Step 5: Conf template** — in `installer/praxiszeit.conf.example` `[database]` add, commented out:

```toml
# Nur Windows: Port der PraxisZeit-eigenen Datenbank (Standard 5432).
# Nur ändern, wenn auf dem Rechner bereits ein anderer PostgreSQL läuft.
# port = 5433
```

- [ ] **Step 6: Add** `tests/test_native_pg_port.py` and `tests/test_native_security_hardening.py` to the pytest list in `scripts/local-ci.sh` step 3.
- [ ] **Step 7: Run** `$NATIVE_TESTS` → all PASS.
- [ ] **Step 8: Commit** `feat(native): configurable PostgreSQL port source on Windows`.

---

### Task 2: Every client uses the port

**Files:**
- Modify: `praxiszeit-server.py` — `pg_env` (:184-206), `pg_is_running` pg_isready argv (:269), `_database_url` (:277-302), `pg_init` managed block (:403)
- Modify: `backend/tests/test_native_pg_lifecycle.py:391-397` (pin test)
- Test: `backend/tests/test_native_pg_port.py`, `backend/tests/test_backup_service.py`

**Interfaces:**
- Consumes: `pg_port()` (Task 1).
- Produces: unchanged signatures; Windows behaviour: `pg_env()` sets `PGHOST="localhost"` and `PGPORT=str(pg_port())`, overriding inherited values; `_database_url(...)` → `postgresql://{cred}@localhost:{pg_port()}/{db}`; `pg_init` writes `port = {pg_port()}`; pg_isready argv carries `-p str(pg_port())`.

- [ ] **Step 1: Failing tests** (`test_native_pg_port.py`, class `TestClientsUsePort`, all with `IS_WINDOWS=True`, `load_config → {"database":{"port":5433}}`):
  - `test_database_url_windows_uses_configured_port` → `== "postgresql://praxiszeit_app:pw@localhost:5433/praxiszeit"`
  - `test_pg_env_windows_overrides_inherited_host_and_port` → with `monkeypatch.setenv("PGPORT","9999")`, `setenv("PGHOST","db.example")`: `env["PGPORT"] == "5433"`, `env["PGHOST"] == "localhost"`
  - `test_pg_isready_probe_uses_configured_port` → captured argv contains `["-p", "5433"]` (spy pattern `TestForeignPgIsolation._capture_run`, `test_native_pg_lifecycle.py:341-352`)
  - `test_pg_init_windows_writes_configured_port` → after `srv.pg_init({...}, "su-pw")` with fake `subprocess.run` (pattern `:399-427`), `postgresql.conf` contains `"\nport = 5433\n"` and `listen_addresses = 'localhost'`
  - `test_unix_url_and_env_unchanged` → Unix URL has no `localhost:`, `PGPORT` not in env.
- [ ] **Step 2: Pin test** — in `test_database_url_windows_uses_tcp` add `monkeypatch.setattr(srv, "load_config", lambda: {})`; assertion stays `localhost:5432` (default unchanged).
- [ ] **Step 3: Backend backup follows the URL** — in `backend/tests/test_backup_service.py` add `test_pg_dump_conn_uses_url_port_on_native_windows_url`: `monkeypatch.setenv("DATABASE_URL_MIGRATIONS", <"postgresql://su:pw@localhost:5433/praxiszeit" built from parts — pre-commit scanner rejects inline-password URL literals>)`; assert the args of `_pg_dump_conn()` contain `"-h", "localhost"` and `"-p", "5433"`. Expected to pass already (`backup_service.py:309-310`) — it is a guard.
- [ ] **Step 4: Run** `$NATIVE_TESTS` → new Windows tests FAIL.
- [ ] **Step 5: Implement** the four call sites. Replace the three `5432` literals; leave docstrings consistent.
- [ ] **Step 6: Run** `$NATIVE_TESTS` → PASS. Run `tests/test_backup_service.py` with the backend unit command from CLAUDE.md → PASS.
- [ ] **Step 7: Commit** `feat(native): route all PostgreSQL clients through the configured port`.

---

### Task 3: Own cluster vs. foreign server

**Files:**
- Modify: `praxiszeit-server.py` — `pg_is_running` (:250-274), `pg_start` (:636-708), `pg_stop` (:711-733), watchdog PG check in `cmd_start` (:2216-2218)
- Test: `backend/tests/test_native_pg_port.py`

**Interfaces:**
- Consumes: `pg_port()`, `ForeignPostgresError`, `EXIT_CONFIG_ERROR` (Task 1).
- Produces:
  - `pg_cluster_state() -> str` — one of `"own"`, `"foreign"`, `"down"`.
    - Unix: `"own"` if pg_isready on the own socket dir succeeds, else `"down"` (today's semantics; the socket dir is already ownership).
    - Windows: pg_isready on `localhost:pg_port()` fails → `"down"`. Answers → `"own"` only if `pg_ctl status -D PG_DATA` returns 0 **and** line 4 (index 3) of `PG_DATA/postmaster.pid` equals `str(pg_port())`; otherwise `"foreign"`. Missing/unreadable pid file → `"foreign"`.
  - `pg_is_running() -> bool` = `pg_cluster_state() == "own"` (zero-arg, unchanged contract).
  - `pg_start()`: first call `pg_cluster_state()`; `"own"` → return; `"foreign"` → `raise ForeignPostgresError(<foreign message>)`; `"down"` → today's start path. The 60-s poll loop also raises `ForeignPostgresError` if the state turns `"foreign"`.
  - `pg_stop()`: only acts on `"own"`.
  - Watchdog: state `"foreign"` → `logger.error(<foreign message>)`, `uvicorn_stop()`, `_remove_pid()`, `sys.exit(EXIT_CONFIG_ERROR)`; `"down"` → today's `pg_start()`.

- [ ] **Step 1: Failing tests** (`TestClusterOwnership`, Windows, tmp `PG_DATA`, `subprocess.run` fake that answers by `Path(argv[0]).name`: `pg_isready` → rc, `pg_ctl` with `status` → rc):
  - `test_down_when_nothing_answers` (isready 2) → `"down"`
  - `test_own_cluster_on_default_port_is_running` (isready 0, pg_ctl status 0, `postmaster.pid` line 4 `5432`, config `{}`) → `"own"`, `pg_is_running() is True`
  - `test_foreign_when_pid_file_missing` (isready 0, status 3) → `"foreign"`, `pg_is_running() is False`
  - `test_foreign_when_pid_file_has_other_port` (isready 0, status 0, line 4 `5432`, config port 5433) → `"foreign"`
  - `test_pg_start_raises_foreign_with_message` → `ForeignPostgresError`, `str(e)` == foreign copy with `5433`; no `net start` in captured argv
  - `test_main_exits_78_on_foreign` → `main()` with `argv ["x","backup"]` and `pg_start` raising → `SystemExit.code == 78`, message in caplog
  - `test_watchdog_exits_on_foreign_server` → drive the watchdog branch (extract it into `_watchdog_check_pg() -> None` so it is testable alone): state `"foreign"` → `SystemExit(78)`, `pg_start` not called
  - `test_pg_stop_ignores_foreign_server` → state `"foreign"`: no `net stop` call
  - `test_unix_semantics_unchanged` → Unix, isready 0 → `"own"` without any `pg_ctl status` call
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** `pg_ctl status` argv: `[str(pg_cmd("pg_ctl")), "status", "-D", str(PG_DATA)]`, `capture_output=True, timeout=10, env=pg_env()`; treat `TimeoutExpired`/`FileNotFoundError` as not own. Read `postmaster.pid` with `errors="replace"`.
- [ ] **Step 4: Run** `$NATIVE_TESTS` (all four files) → PASS; existing `TestCmdStartBranching`, `TestLostCredentialsFailFast`, restore tests unchanged and green.
- [ ] **Step 5: Commit** `fix(native): tell the own PostgreSQL cluster from a foreign server on Windows`.

---

### Task 4: Existing clusters pick up the configured port

**Files:**
- Modify: `praxiszeit-server.py` — new helper near `pg_init`; call in `cmd_start` between the init decision (:2123-2126) and `pg_start()` (:2129); new CLI `sync-db-port`
- Test: `backend/tests/test_native_pg_port.py`

**Interfaces:**
- Consumes: `pg_port()`, `_win_service_exists(name)` (:519), `PG_SERVICE_NAME`.
- Produces:
  - `sync_managed_pg_port(conf_path: Path, port: int) -> bool` — pure file edit, returns `True` if the file changed. Rule: find the line `# PraxisZeit configuration`; replace the first **uncommented** line matching `^\s*port\s*=` after it with `port = {port}`. Header present but no port line → insert `port = {port}` directly after the header. Header missing → if `port != 5432` append `\n# PraxisZeit configuration\nport = {port}\n`, else no change. Never touch lines before the header (initdb's `#port = 5432`). Preserve line endings and encoding (read/write bytes or `newline=""`).
  - `apply_pg_port() -> bool` — Windows only (Unix → `False`): if `PG_DATA/postgresql.conf` exists, call `sync_managed_pg_port(..., pg_port())`; if it changed and `_win_service_exists(PG_SERVICE_NAME)`, run `net stop PraxisZeit-PostgreSQL` (return code ignored; it may not run). Logs `PostgreSQL-Port in postgresql.conf auf {port} gesetzt`.
  - `cmd_start` calls `apply_pg_port()` right before `pg_start()`.
  - CLI `sync-db-port` → `cmd_sync_db_port(args)`: calls `apply_pg_port()`, prints nothing on stdout. (Used by restore-backup.bat, Task 5.)

- [ ] **Step 1: Failing tests** (`TestManagedConfPortSync`, files in tmp_path; fixture conf = initdb-like text with `#port = 5432 # (change requires restart)` early, then `\n# PraxisZeit configuration\nlisten_addresses = 'localhost'\nport = 5432\nmax_connections = 50\n`):
  - `test_sync_is_noop_for_default_conf` → port 5432: returns `False`, bytes identical
  - `test_sync_rewrites_only_managed_line` → 5433: returns `True`; managed line `port = 5433`; `#port = 5432` line unchanged; all other lines byte-identical
  - `test_sync_is_idempotent` → second call returns `False`
  - `test_sync_keeps_crlf` → CRLF fixture stays CRLF
  - `test_sync_appends_block_when_header_missing` → no header, 5433 → block appended; no header, 5432 → unchanged
  - `test_changed_port_stops_running_service_before_start` → Windows, config 5433, conf at 5432, `_win_service_exists → True`: argv log contains `["net","stop","PraxisZeit-PostgreSQL"]` and comes before any `net start`/`pg_ctl register`
  - `test_cmd_start_branching_unaffected` → run one existing `TestCmdStartBranching` path with Windows + `{}` config and assert no `net stop` recorded (guards Review Focus 1)
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** helpers, hook, subcommand.
- [ ] **Step 4: Run** `$NATIVE_TESTS` → PASS.
- [ ] **Step 5: Commit** `feat(native): rewrite the managed postgresql.conf port on start`.

---

### Task 5: Windows batch files and the service

**Files:**
- Modify: `installer/windows/restore-backup.template.bat` (:57-64 variables; before `"%PG_CTL%" ... start` :119)
- Modify: `installer/windows/uninstall.bat` (:66-78)
- Modify: `installer/windows/setup.bat` (:116-127, `--serverport`)
- Modify: `installer/windows/install-service.bat` (NSSM block :30-43)
- Modify: `installer/windows/update-wizard.ps1` (service step; idempotent)
- Test: `backend/tests/test_native_restore.py` (Windows text section :589-756), new text tests in `backend/tests/test_native_pg_port.py`

**Interfaces:**
- Consumes: CLI `print-db-port` (Task 1), `sync-db-port` (Task 4), `EXIT_CONFIG_ERROR = 78`.
- Produces: batch behaviour only.

Decisions:
- **restore-backup**: after `PYTHON`/`SERVER` are set, `"%PYTHON%" "%DIR%\praxiszeit-server.py" sync-db-port` + `if errorlevel 1 goto <existing error label>`; then `for /f "usebackq delims=" %%p in (`"%PYTHON%" "%DIR%\praxiszeit-server.py" print-db-port`) do SET "DB_PORT=%%p"`; `if not defined DB_PORT goto <error label>`. `PSQL_ARGS` becomes `-X -w -q -v ON_ERROR_STOP=1 -U praxiszeit -h localhost -p %DB_PORT%`. ASCII only, CRLF.
- **uninstall.bat**: same `for /f` port read (fallback `5432` if Python fails — uninstall must not abort); `pg_dump` gets `-h localhost -p %DB_PORT%`.
- **setup.bat**: `--serverport` gets the port from `print-db-port` when Python already exists at that point; otherwise `5432`. Comment (no parentheses inside the `()` block, see :108-109): the EDB service is deleted right after install, the real port handling is at service start. The system-PG reuse branch (:60-91) needs no change.
- **NSSM**: `"%NSSM%" set PraxisZeit AppExit 78 Exit` in `install-service.bat`; `update-wizard.ps1` runs the same `nssm set` for existing installations (ignore errors if NSSM/service missing). `WindowsPlatform.InstallServiceAsync` is unused — leave it.

- [ ] **Step 1: Failing tests.** In `test_native_restore.py` (reuse `_bat_text`/`_BAT` helpers):
  - `test_restore_bat_reads_db_port_from_server_script` → text contains `print-db-port`, `SET "DB_PORT=`, and the `SET "PSQL_ARGS=` line contains `-h localhost` and `-p %DB_PORT%` and no `5432`
  - `test_restore_bat_syncs_port_before_cluster_start` → index of `sync-db-port` < index of the `"%PG_CTL%"` line containing ` start`
  - existing `test_restore_bat_hat_durchgehend_crlf`, `test_restore_bat_prueft_jeden_schritt` stay green (run, do not edit)
  - In `test_native_pg_port.py` class `TestWindowsScripts` (read files as bytes, decode `utf-8`, assert `\r\n`): `test_uninstall_dump_uses_db_port` (`pg_dump` line has `-p %DB_PORT%`, file CRLF), `test_install_service_sets_appexit_78` (`AppExit 78 Exit`), `test_update_wizard_sets_appexit_78`, `test_setup_bat_serverport_not_hardcoded` (no `--serverport 5432`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the five files. Convert with `perl -0777 -i -pe 's/\r?\n/\r\n/g'` only if an editor broke CRLF; check `file installer/windows/*.bat`.
- [ ] **Step 4: Run** `$NATIVE_TESTS` → PASS.
- [ ] **Step 5: Commit** `feat(windows): batch files and service follow the configured database port`.

---

### Task 6: GUI installer — database port field

**Files:**
- Modify: `installer/setup/src/PraxisZeit.Setup.Core/Services/PraxisZeitConfigWriter.cs` (record :14-42, `ValidateValues` :79-118, `Serialize` [database] :142-146)
- Create: `installer/setup/src/PraxisZeit.Setup.Core/Services/PortConflictChecker.cs`
- Modify: `installer/setup/src/PraxisZeit.Setup/ViewModels/PortsPageViewModel.cs` (:14-127), `Views/PortsPageView.axaml` (:24, cards :31-53), `ViewModels/MainWindowViewModel.cs` (`BuildConfigValues` :426-434)
- Test: `installer/setup/tests/PraxisZeit.Setup.Core.Tests/Services/PraxisZeitConfigWriterTests.cs`, new `PortConflictCheckerTests.cs`

**Interfaces:**
- Produces:
  - `PraxisZeitConfigValues.DbPort { get; init; } = 5432`
  - `ValidateValues`: `DbPort` outside 1024–65535 → `"Datenbank-Port muss zwischen 1024 und 65535 liegen."`; equal to `HttpsPort` or effective `HttpRedirectPort` → `"Datenbank-Port darf nicht gleich dem HTTPS- oder HTTP-Port sein."`
  - `Serialize`: `[database]` gets `port = {DbPort}` only when `DbPort != 5432` (default conf stays byte-identical to today).
  - `public static class PortConflictChecker { public static IReadOnlyList<string> Conflicts(IReadOnlyDictionary<string,int> labelledPorts, ISet<int> busyPorts); }` — returns labels whose port is busy. Moves the pure part out of `CheckPortConflicts()` so it is testable (the GUI project has no tests).
  - `PortsPageViewModel.DbPort` (`[ObservableProperty]`, default 5432, `partial void OnDbPortChanged => Validate()`), card “Datenbank-Port (nur Windows)” with help text `Nur ändern, wenn auf diesem Rechner bereits ein anderer PostgreSQL läuft (z. B. 5433).` Busy DB port → own warning `Achtung: Datenbank-Port {p} ist bereits belegt – vermutlich läuft hier schon ein anderer PostgreSQL. Wählen Sie einen freien Port, z. B. 5433.` (web-server warning unchanged for 443/80). Card visible only on Windows (`OperatingSystem.IsWindows()`).
  - `BuildConfigValues` passes `DbPort = _ports.DbPort`.

- [ ] **Step 1: Failing xunit tests:** `Serialize_omits_db_port_at_default` (no `port =` line between `[database]` and the next `[`), `Serialize_writes_custom_db_port_in_database_section` (section-scoped: slice text from `[database]` to next `\n[` contains `port = 5433`; `[server]` slice unchanged), `ValidateValues_rejects_db_port_out_of_range` ([Theory] 0, 1023, 65536), `ValidateValues_rejects_db_port_equal_to_https`, `PortConflictCheckerTests.Returns_label_of_busy_db_port`, `Returns_empty_when_nothing_busy`.
- [ ] **Step 2: Run** `dotnet test installer/setup/PraxisZeit.Setup.slnx -c Release --nologo` → FAIL.
- [ ] **Step 3: Implement** Core changes, then VM/View/MainWindow.
- [ ] **Step 4: Run** `dotnet test …` → PASS; `dotnet build installer/setup/PraxisZeit.Setup.slnx -c Release` → 0 errors. Update the test count in `docs/BUILD-RELEASE.md:66` if it is quoted.
- [ ] **Step 5: Commit** `feat(setup): database port field on the ports page`.

---

### Task 7: Emulator harness and real Windows proof

**Files:**
- Modify: `tools/win-test/oem/install.bat` (:52 conf build, :86-90), `tools/win-test/share/post-reboot.bat` (:31-34), `docs/WINDOWS-EMULATOR-TEST.md` (mode list :16-19, :89-94)

**Interfaces:**
- Consumes: everything above, via a built Windows zip (`tools/build-release.sh`, see `docs/BUILD-RELEASE.md`; wine-binfmt `DOSWin` needed).
- Produces: harness mode `foreignpg`, result keys in `share/install-result.txt`.

Decisions:
- All four `5432` literals become `%DB_PORT%`, read via `print-db-port` after setup (CRLF stays).
- New `mode.txt` value `foreignpg`: before `setup.bat`, initdb a throw-away cluster with the bundled binaries into `C:\foreignpg` and `pg_ctl start -o "-p 5432"`; append `[database]`-section `port = 5433` to the generated conf (line 52 builds it from the example — insert after the `[database]` header). After install: write `FOREIGN_PG_STILL_ON_5432=` (pg_isready on 5432) and `DB_PORT=5433`, run `praxiszeit-server.py backup` and `restore-backup.bat <that file>` non-interactively, write `RESTORE_EXIT=`.
- Extra negative check in `foreignpg`: before setting 5433, start the service once with the default conf → `logs\service-stderr.log` contains `ist von einem anderen PostgreSQL belegt`, service stays stopped (NSSM `AppExit 78 Exit`) → `FOREIGN_DETECTED=1`.

- [ ] **Step 1: Implement** harness changes; `file tools/win-test/oem/install.bat tools/win-test/share/post-reboot.bat` → CRLF.
- [ ] **Step 2: Build** the Windows zip from this branch.
- [ ] **Step 3: Scenario (a) update** — `share/tree-old` = 1.22.0 zip, `mode.txt` = `update`, no port entry. `cd tools/win-test && docker compose down -v && docker compose up -d`; wait `until grep -qaF -e '===== DONE =====' share/install-result.txt; do sleep 60; done` (run in background/Monitor; fish: one-liner). Expected: `HEALTH_HTTP=200`, `LOGIN_HTTP=200`, `ALEMBIC_VERSION=075`, `BACKUP_EXIT=0`, `postgresql.conf` unchanged (harness prints `md5` before/after).
- [ ] **Step 4: Scenario (b) foreignpg** — `mode.txt` = `foreignpg`. Expected: `FOREIGN_DETECTED=1`, then `HEALTH_HTTP=200`, `LOGIN_HTTP=200`, `DB_PORT=5433`, `FOREIGN_PG_STILL_ON_5432=0`, `BACKUP_EXIT=0`, `RESTORE_EXIT=0`, reboot keys green.
- [ ] **Step 5: Record** both result files' key lines in the PR description. Do not edit memory files of the release process here.
- [ ] **Step 6: Commit** `test(win-test): foreign PostgreSQL scenario and configurable port`.

---

### Task 8: Documentation and changelog

**Files:**
- Modify: `docs/NATIVE-BETRIEB.md:20` (rule “drei Stellen” → four: `pg_is_running`/`pg_cluster_state`, `_database_url`, `pg_init` listen+port, `pg_env`; Windows port now configurable; conf-rewrite tech debt resolved for `port`), `docs/INSTALL-NATIVE.md` (Konfiguration block :175-216 gets `[database]` with commented `port`; Fehlerbehebung table :368 new row “Port {p} ist von einem anderen PostgreSQL belegt” → `[database] port`), `docs/NATIVE-WINDOWS-PITFALLS.md` (:270 checklist wording; new pitfall #13 “Fremder PostgreSQL auf 5432”), `docs/setup-windows.md` (:53-60 “Bestehendes PostgreSQL?” → port setting; :68 table row “5432 oder `[database] port`”), `docs/setup-anleitung.md` (:83, :434-437, :799), `docs/ARC42.md:573` (risk downgraded: detected and configurable), `docs/UPDATE.md` Windows section (:293-305: first start may rewrite the port line; nothing to do), `CHANGELOG.md` (new `## [Unreleased]` above `## [1.22.0]` with `### ✨ Neu` and a `### ⚠️ Hinweis` that a GUI repair resets the DB port to the field value), `scripts/check-doc-sync.sh` (new `group_db_port`: `need praxiszeit-server.py 'ist von einem anderen PostgreSQL belegt'`, `need docs/INSTALL-NATIVE.md 'ist von einem anderen PostgreSQL belegt'`, `need docs/setup-windows.md '[database]'`), `CLAUDE.md` (one rule line under “Lizenz, Updater, Native-Betrieb”: port source `pg_port()`, ownership `pg_cluster_state`, exit 78/NSSM, Windows only; and fix the location of the native tests: `backend/tests/`, not repo root)
- Separate repo: `~/claude/pzweb/frontend/src/pages/marketing/anleitung/AnleitungWindows.tsx` Card “Netzwerk und Port” (:198-279): subsection “Anderer PostgreSQL auf dem Rechner” + `AnleitungWindows.test.tsx` (run in docker `node:20`, not alpine). Own branch + PR in pzweb, merged together with the release.

- [ ] **Step 1: Write** the docs. Copy the foreign-server message verbatim from Global Constraints.
- [ ] **Step 2: Run** `bash scripts/check-doc-sync.sh all` → exit 0.
- [ ] **Step 3: pzweb** — branch `docs/windows-db-port`, edit + test: `docker run --rm -v "$PWD/frontend":/app -w /app node:20 sh -c "npx vitest run src/pages/marketing/anleitung/AnleitungWindows.test.tsx --pool=threads"` → PASS; open PR, do not merge.
- [ ] **Step 4: Full gates** — `$NATIVE_TESTS`, backend unit suite (CLAUDE.md command, `-e TZ=Europe/Berlin`), `dotnet test …`, `bash scripts/check-doc-sync.sh all`. All green.
- [ ] **Step 5: Commit** `docs: configurable PostgreSQL port on Windows`, push, open PR against master with the emulator results from Task 7.
