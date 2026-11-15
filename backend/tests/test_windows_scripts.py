"""Text-level checks for the Windows installer scripts (log audit 2026-11-15).

cmd.exe and Windows PowerShell are not available in CI; these tests pin the
structure of update-wizard.ps1, install-service.bat, backup.bat and
restore-backup.template.bat that the customer log audit of 2026-11-15
(items A1, A4, A5, A11, A13, A14, A18, A19) asked for.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_WIN = _REPO / "installer" / "windows"

_SCRIPTS = [
    "backup.bat",
    "install-service.bat",
    "restore-backup.template.bat",
    "setup.bat",
    "uninstall.bat",
    "uninstall-service.bat",
    "update-wizard.bat",
    "update-wizard.ps1",
    "secure-install.ps1",
]

# Diese beiden enthielten schon vor dem Log-Audit Nicht-ASCII-Zeichen.
_NON_ASCII = {"uninstall.bat", "update-wizard.ps1"}


def _raw(name: str) -> bytes:
    return (_WIN / name).read_bytes()


def _text(name: str) -> str:
    raw = _raw(name)
    assert b"\n" not in raw.replace(b"\r\n", b""), f"{name} braucht CRLF"
    return raw.decode("utf-8")


def _function(text: str, name: str) -> str:
    """Body of a PowerShell function up to the next top-level ``function``."""
    start = text.index(f"function {name}")
    nxt = text.find("\r\nfunction ", start + 1)
    return text[start:nxt if nxt != -1 else len(text)]


def _label_block(text: str, label: str) -> str:
    lines = text.split("\r\n")
    start = next(i for i, line in enumerate(lines) if line.strip().lower() == f":{label}")
    out = []
    for line in lines[start + 1:]:
        if line.startswith(":") and not line.startswith("::"):
            break
        out.append(line)
    return "\r\n".join(out)


@pytest.mark.parametrize("name", _SCRIPTS)
def test_script_is_crlf(name):
    raw = _raw(name)
    assert b"\n" not in raw.replace(b"\r\n", b""), f"{name} braucht CRLF"
    if name not in _NON_ASCII:
        raw.decode("ascii")


@pytest.mark.parametrize("name", [n for n in _SCRIPTS if n.endswith(".bat")]
                         + ["../../tools/win-test/oem/install.bat"])
def test_bat_echo_in_block_has_no_closing_paren(name):
    # Eine ')' im echo-Text innerhalb eines if/for-Blocks schliesst den Block
    # vorzeitig - cmd.exe bricht dann still ab (Release 1.20.2).
    depth = 0
    for no, line in enumerate(_raw(name).decode("utf-8").split("\r\n"), 1):
        s = line.strip()
        if s.upper().startswith("REM") or s.startswith("::"):
            continue
        if s.startswith(")"):
            depth = max(0, depth - 1)
        low = s.lower()
        if depth > 0 and re.match(r"^(>>\s*\"[^\"]*\"\s*)?@?echo[ .]", low):
            assert ")" not in s.split("echo", 1)[1].replace("^)", ""), f"{name}:{no}: {line}"
        if s.endswith("(") and not low.startswith("echo"):
            depth += 1


# --- A5 / A11: NSSM-Neustart-Bremse und Log-Rotation --------------------------

_NSSM_SETTINGS = (
    "AppExit 78 Exit",
    "AppStopMethodConsole 30000",
    "AppThrottle 1500",
    "AppRestartDelay 60000",
    "AppRotateFiles 1",
    "AppRotateOnline 1",
    "AppRotateBytes 10485760",
)


@pytest.mark.parametrize("setting", _NSSM_SETTINGS)
def test_install_service_sets_nssm_option(setting):
    assert f'"%NSSM%" set PraxisZeit {setting}' in _text("install-service.bat")


def test_wizard_sets_all_nssm_options_in_one_place():
    text = _text("update-wizard.ps1")
    body = _function(text, "Set-NssmServiceOptions")
    for setting in _NSSM_SETTINGS:
        parts = setting.split()
        assert "'" + "', '".join(parts) + "'" in body or "@('" + "', '".join(parts) + "')" in body, setting


# --- A1: Dienst-Stopp im Update ----------------------------------------------

def test_stop_sets_nssm_options_before_stopping():
    body = _function(_text("update-wizard.ps1"), "Step-StopService")
    assert body.index("Set-NssmServiceOptions") < body.index("Stop-Service -Name 'PraxisZeit' ")


def test_stop_also_stops_the_postgresql_service():
    body = _function(_text("update-wizard.ps1"), "Step-StopService")
    stop_app = body.index("Stop-Service -Name 'PraxisZeit' ")
    stop_pg = body.index("Stop-Service -Name 'PraxisZeit-PostgreSQL'")
    assert stop_app < stop_pg
    assert "WaitForStatus('Stopped', (New-TimeSpan -Seconds 60))" in body[stop_pg:]


def test_stop_logs_both_service_states_before_and_after():
    text = _text("update-wizard.ps1")
    log = _function(text, "Write-ServiceStates")
    assert "sc.exe" in log and "'PraxisZeit', 'PraxisZeit-PostgreSQL'" in log
    body = _function(text, "Step-StopService")
    assert body.count("Write-ServiceStates") >= 2
    assert body.index("Write-ServiceStates") < body.index("Stop-Service -Name 'PraxisZeit' ")


def test_stop_kills_leftover_python_from_the_install_dir():
    text = _text("update-wizard.ps1")
    left = _function(text, "Stop-LeftoverPython")
    assert "Get-CimInstance Win32_Process" in left
    assert "ExecutablePath" in left and "bin\\python" in left
    assert "Stop-Process" in left
    body = _function(text, "Step-StopService")
    assert body.index("Stop-Service -Name 'PraxisZeit' ") < body.index("Stop-LeftoverPython")


def test_start_starts_only_the_app_service():
    body = _function(_text("update-wizard.ps1"), "Step-StartService")
    assert "Set-NssmServiceOptions" in body
    assert "Start-Service -Name 'PraxisZeit'" in body
    assert "Start-Service -Name 'PraxisZeit-PostgreSQL'" not in body
    assert "net start" not in body.lower()


def test_failed_stop_restarts_the_old_version():
    upd = _function(_text("update-wizard.ps1"), "Invoke-Update")
    ok3 = upd.index("if (-not $ok3)")
    block = upd[ok3:upd.index("Step-CopyFiles")]
    assert "Step-StartService" in block


# --- A4 / A14: Sicherung vor dem Update --------------------------------------

def test_backup_uses_preupdate_label_with_fallback_for_old_server():
    body = _function(_text("update-wizard.ps1"), "Step-Backup")
    assert "backup --label $label" in body
    assert "preupdate-" in body
    # Fallback ohne Argument, wenn das ALTE Serverskript --label nicht kennt
    assert "$rc -eq 2" in body and "unrecognized arguments" in body
    assert '"-I -S -X utf8 $quotedServer backup"' in _text("update-wizard.ps1")


def test_backup_verifies_a_new_non_empty_file():
    body = _function(_text("update-wizard.ps1"), "Step-Backup")
    assert "Get-BackupFiles" in body
    files = _function(_text("update-wizard.ps1"), "Get-BackupFiles")
    assert "data\\backups" in files and "*.sql.gz" in files
    assert "Length -gt 0" in body


def test_backup_failure_asks_in_gui_and_aborts_headless():
    text = _text("update-wizard.ps1")
    fail = _function(text, "Resolve-BackupFailure")
    assert "YesNo" in fail
    assert "if ($Headless)" in fail
    assert "ContinueWithoutBackup" in fail
    upd = _function(text, "Invoke-Update")
    ok2 = upd.index("if (-not $ok2)")
    assert ok2 < upd.index("Step-StopService")
    assert "return $false" in upd[ok2:upd.index("Step-StopService")]


def test_backup_starts_postgresql_when_the_app_is_stopped():
    # Reparieren nach abgebrochenem Update: beide Dienste stehen, "backup"
    # braucht aber einen laufenden Cluster.
    body = _function(_text("update-wizard.ps1"), "Step-Backup")
    assert "Start-Service -Name 'PraxisZeit-PostgreSQL'" in body


# --- Klarer naechster Schritt nach einem Fehler hinter dem Kopieren ----------

def test_failure_after_copy_prints_next_steps():
    text = _text("update-wizard.ps1")
    guide = _function(text, "Write-FailureGuidance")
    assert "Reparieren" in guide
    assert "unveraendert" in guide
    assert "$script:BackupFile" in guide
    copy = _function(text, "Step-CopyFiles")
    assert "$script:FilesCopied = $true" in copy
    done = _function(text, "Show-Done")
    assert "Write-FailureGuidance" in done


# --- A13: Sicherungsaufgabe holt verpasste Laeufe nach -----------------------

def test_wizard_registers_task_with_start_when_available():
    body = _function(_text("update-wizard.ps1"), "Step-ScheduledTask")
    assert "Register-ScheduledTask" in body
    assert "-StartWhenAvailable" in body
    assert "-Daily -At '03:00'" in body
    assert "-UserId 'SYSTEM'" in body
    # Rueckfall fuer Systeme ohne ScheduledTasks-Modul
    assert "schtasks /create" in body


def test_install_service_registers_task_with_start_when_available():
    text = _text("install-service.bat")
    line = next(l for l in text.split("\r\n")
                if "Register-ScheduledTask" in l and not l.startswith("REM"))
    assert line.startswith("powershell ")
    assert "-StartWhenAvailable" in line and "-Daily -At '03:00'" in line
    assert "-UserId 'SYSTEM'" in line and "$env:BACKUP_BAT" in line
    assert "%" not in line.replace("%BACKUP_BAT%", "")
    assert "schtasks /create" in text  # Rueckfall


# --- A18: Wiederherstellung startet/stoppt den Datenbankdienst ---------------

def test_restore_stops_pg_via_service():
    text = _text("restore-backup.template.bat")
    stop = _label_block(text, "pg_stop")
    assert "net stop PraxisZeit-PostgreSQL" in stop
    # pg_ctl stop nur noch fuer den selbst per pg_ctl gestarteten Cluster
    for line in text.split("\r\n"):
        if line.startswith('"%PG_CTL%"') and " stop" in line:
            assert line in stop.split("\r\n"), line
    main = text[:text.index("\r\n:backup_unbrauchbar")]
    assert "call :pg_stop" in main


def test_restore_uses_pg_ctl_start_only_as_fallback():
    text = _text("restore-backup.template.bat")
    lines = text.split("\r\n")
    svc = lines.index("net start PraxisZeit-PostgreSQL >nul 2>&1")
    start = next(i for i, l in enumerate(lines) if l.startswith('"%PG_CTL%"') and " start" in l)
    assert svc < start
    between = "\r\n".join(lines[svc:start])
    assert "call :pg_wait" in between
    assert 'if "%PG_VIA_CTL%"=="1" (' in between
    assert lines[start + 1] == ")"
    wait = _label_block(text, "pg_wait") + _label_block(text, "pg_wait_loop")
    assert "%PG_ISREADY%" in wait and "-p %DB_PORT%" in wait


def test_restore_error_paths_stop_pg_through_the_helper():
    text = _text("restore-backup.template.bat")
    for label in ("bestand_unveraendert", "tausch_gescheitert", "rechte_gescheitert"):
        assert "call :pg_stop" in _label_block(text, label), label


# --- A19: backup.bat ohne Administratorrechte --------------------------------

def test_backup_bat_checks_admin_rights_first():
    text = _text("backup.bat")
    check = text.index("net session >nul 2>&1")
    assert check < text.index('"%PYTHON%" "%SERVER%" backup')
    hint = text[check:text.index('"%PYTHON%" "%SERVER%" backup')]
    assert "Administrator" in hint and "exit /b 1" in hint


# --- Review-Nachzug 2026-11-15 ----------------------------------------------

def test_backup_treats_every_non_running_state_as_stopped():
    # NSSM-Drosselung: zwischen den Abstuerzen steht der Dienst auf Paused/
    # StartPending - auch das ist "PraxisZeit laeuft nicht".
    body = _function(_text("update-wizard.ps1"), "Step-Backup")
    assert "$appSvc.Status -ne 'Running'" in body
    assert "$appSvc.Status -eq 'Stopped'" not in body
    assert "$script:AppWasStopped" in body


def test_headless_repair_continues_without_age_limit_when_app_is_down():
    # Setup.exe ruft immer -Headless ohne -ContinueWithoutBackup auf: steht
    # PraxisZeit schon, schuetzt ein Abbruch nichts - Reparieren muss gehen.
    fail = _function(_text("update-wizard.ps1"), "Resolve-BackupFailure")
    assert "AddHours(-24)" not in fail
    head = fail[fail.index("if ($Headless)"):fail.index("$txt = ")]
    down = head.index("if ($appWasStopped)")
    assert down < head.index("return $false")
    assert "return $true" in head[down:head.index("return $false")]


def test_abort_messages_depend_on_app_state():
    text = _text("update-wizard.ps1")
    fail = _function(text, "Resolve-BackupFailure")
    assert "weiterhin gestoppt" in fail
    guide = _function(text, "Write-FailureGuidance")
    assert "$script:AppWasStopped" in guide
    assert "weiterhin gestoppt" in guide


def test_abort_stops_postgresql_started_for_the_backup():
    text = _text("update-wizard.ps1")
    assert "$script:PgStartedForBackup = $true" in _function(text, "Step-Backup")
    upd = _function(text, "Invoke-Update")
    ok2 = upd[upd.index("if (-not $ok2)"):upd.index("Step-StopService")]
    assert "$script:PgStartedForBackup" in ok2
    assert "Stop-Service -Name 'PraxisZeit-PostgreSQL'" in ok2


def test_guidance_after_failed_start_does_not_claim_unchanged_database():
    guide = _function(_text("update-wizard.ps1"), "Write-FailureGuidance")
    assert "$script:FailedStep -eq 'Service starten'" in guide
    assert "Migrationen" in guide


def test_service_state_line_matches_german_status():
    log = _function(_text("update-wizard.ps1"), "Write-ServiceStates")
    assert "STATUS" in log and "STATE" in log
    assert "^\\s*(STATE|STATUS|ZUSTAND)\\s*:" in log


def test_restore_waits_with_ping_not_timeout():
    # timeout bricht bei umgeleiteter Eingabe sofort ab (win-test-Harness
    # ruft restore-backup.bat mit "< pz-confirm.txt" auf).
    text = _text("restore-backup.template.bat")
    for line in text.split("\r\n"):
        assert not line.strip().lower().startswith("timeout "), line
    assert "ping -n 2 127.0.0.1 >nul" in _label_block(text, "pg_wait_loop")


def test_app_throttle_stays_short():
    """Emulator 1.24.1: NSSM haelt den Dienst fuer AppThrottle in START_PENDING;
    mit 150000 stoppte Windows ihn nach ~20 s per Ctrl+C mitten im Start."""
    import re
    for name, pattern in (
        ("install-service.bat", r'set PraxisZeit AppThrottle (\d+)'),
        ("update-wizard.ps1", r"@\('AppThrottle', '(\d+)'\)"),
    ):
        values = [int(v) for v in re.findall(pattern, _text(name))]
        assert values, name
        assert all(v <= 10000 for v in values), (name, values)

# --- Windows-Server-Update 2026-11-15 (Lauf 1 gescheitert, Lauf 2 ok) -------
# Lauf 1: robocopy FEHLER 32 auf nssm.exe ohne Hinweis, wer die Datei sperrt;
# ACL-Pruefung "Dem Client fehlt ein erforderliches Recht" ohne Details;
# Abschlussmeldung "NICHT gestartet", obwohl der Dienst lief.


def test_update_logs_environment_first():
    upd = _function(_text("update-wizard.ps1"), "Invoke-Update")
    assert upd.index("Write-Environment") < upd.index("Step-ACLFix")
    env = _function(_text("update-wizard.ps1"), "Write-Environment")
    for needle in ("Win32_OperatingSystem", "ProductType", "SessionId",
                   "IsInRole", "PSVersion", "$env:TEMP", "Is64BitProcess"):
        assert needle in env, needle


def test_locked_files_name_the_locking_process():
    text = _text("update-wizard.ps1")
    who = _function(text, "Write-FileLockers")
    assert "rstrtmgr.dll" in text
    assert "RmGetList" in text
    # Fallback ohne Restart Manager: Prozesse aus dem Installationsordner.
    assert "Win32_Process" in who


def test_copy_retries_once_after_lock_with_diagnosis():
    body = _function(_text("update-wizard.ps1"), "Step-CopyFiles")
    assert "Get-LockedPaths" in body
    assert "Write-FileLockers" in body
    assert "Stop-LeftoverInstallProcesses" in body
    assert body.count("robocopy.exe @rcArgs") >= 2


def test_leftover_processes_cover_whole_install_dir():
    body = _function(_text("update-wizard.ps1"), "Stop-LeftoverInstallProcesses")
    assert "ExecutablePath" in body and "ParentProcessId" in body
    assert "$PID" in body
    stop = _function(_text("update-wizard.ps1"), "Step-StopService")
    assert "Stop-LeftoverInstallProcesses" in stop


def test_start_waits_for_postgresql_before_logging_state():
    body = _function(_text("update-wizard.ps1"), "Step-StartService")
    assert "Wait-PostgresService" in body
    assert body.index("Wait-PostgresService") < body.index("Write-ServiceStates 'nach dem Start'")


def test_guidance_reports_the_real_service_state():
    guide = _function(_text("update-wizard.ps1"), "Write-FailureGuidance")
    assert "Get-Service -Name 'PraxisZeit'" in guide
    assert "teilweise aktualisiert" in guide


def test_secure_install_logs_add_type_details():
    text = _text("secure-install.ps1")
    catch = text[text.index("Add-Type -Language CSharp -TypeDefinition $PzFileLinksCode"):]
    catch = catch[:catch.index("exit 1")]
    assert "Write-PzAddTypeFailure $_.Exception" in catch
    helper = _function(text, "Write-PzAddTypeFailure")
    for needle in ("GetType().FullName", "HResult", "InnerException", "$env:TEMP"):
        assert needle in helper, needle

