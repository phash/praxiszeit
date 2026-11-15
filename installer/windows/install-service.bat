@echo off
setlocal DisableDelayedExpansion
REM PraxisZeit Windows Service Installation
REM Requires nssm.exe in the same directory or in PATH

SET "INSTALL_DIR=%~dp0."
SET "NSSM=%~dp0nssm.exe"
SET "PYTHON=%INSTALL_DIR%\bin\python\python.exe"
SET "SCRIPT=%INSTALL_DIR%\praxiszeit-server.py"

echo PraxisZeit Windows Service Installer
echo =====================================

REM Check if nssm exists
if not exist "%NSSM%" (
    echo ERROR: nssm.exe not found at %NSSM%
    echo Download from https://nssm.cc/download
    if not defined PRAXISZEIT_NONINTERACTIVE pause
    exit /b 1
)

REM Check if Python exists
if not exist "%PYTHON%" (
    echo ERROR: Python not found at %PYTHON%
    if not defined PRAXISZEIT_NONINTERACTIVE pause
    exit /b 1
)

REM Install service
echo Installing PraxisZeit service...
"%NSSM%" install PraxisZeit "%PYTHON%" "%SCRIPT%" start
"%NSSM%" set PraxisZeit AppDirectory "%INSTALL_DIR%"
"%NSSM%" set PraxisZeit DisplayName "PraxisZeit Zeiterfassung"
"%NSSM%" set PraxisZeit Description "Zeiterfassungssystem fuer Arztpraxen"
"%NSSM%" set PraxisZeit Start SERVICE_AUTO_START
"%NSSM%" set PraxisZeit AppStdout "%INSTALL_DIR%\logs\service-stdout.log"
"%NSSM%" set PraxisZeit AppStderr "%INSTALL_DIR%\logs\service-stderr.log"
REM Exit-Code 78 = Konfigurationsfehler (z.B. ungueltiger Datenbank-Port): NSSM
REM soll den Dienst dann beenden statt ihn endlos neu zu starten.
"%NSSM%" set PraxisZeit AppExit 78 Exit
REM Nach Ctrl+C bis zu 30 s auf den sauberen Shutdown warten (uvicorn_stop +
REM PostgreSQL-Dienst stoppen). NSSM-Standard 1500 ms beendete den Dienst hart,
REM PostgreSQL lief beim Update weiter (Kundenfall 2026-11-15).
"%NSSM%" set PraxisZeit AppStopMethodConsole 30000
REM Neustart-Bremse (Log-Audit 2026-11-15 A5): bei einem Startfehler startete
REM NSSM den Dienst im Minutentakt neu, 5521 Mal in 4 Tagen, die stderr-Datei
REM wuchs auf 16 MB. Laeuft das Programm kuerzer als AppThrottle (150 s), bremst
REM NSSM den naechsten Start; jeder Neustart wartet mindestens AppRestartDelay.
REM Ein Lauf dauerte im Kundenfall 62 s - 60 s haette nicht gebremst.
"%NSSM%" set PraxisZeit AppThrottle 150000
"%NSSM%" set PraxisZeit AppRestartDelay 15000
REM Log-Rotation auch im laufenden Betrieb (Log-Audit A11): ohne AppRotateOnline
REM rotiert NSSM nur beim Dienststart, Anmeldenamen und IP-Adressen aus
REM fehlgeschlagenen Logins blieben monatelang in einer Datei.
"%NSSM%" set PraxisZeit AppRotateFiles 1
"%NSSM%" set PraxisZeit AppRotateOnline 1
"%NSSM%" set PraxisZeit AppRotateBytes 10485760
REM PYTHONUNBUFFERED: ohne das puffert Python stdout/stderr, und Startup-Fehler
REM (z.B. ein haengendes DB-Setup) landen erst beim Prozess-Ende - oder nie - in
REM service-stdout/stderr.log. PYTHONUTF8: cp1252-Crashes bei Umlauten/Emojis vermeiden.
"%NSSM%" set PraxisZeit AppEnvironmentExtra PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONNOUSERSITE=1

echo.
echo Service installed successfully.
echo Start with: net start PraxisZeit
echo Stop with:  net stop PraxisZeit
echo.

REM Add firewall rule
echo Adding firewall rule...
netsh advfirewall firewall add rule name="PraxisZeit" dir=in action=allow protocol=TCP localport=443
echo Firewall rule added for port 443.

REM ============================================================
REM Scheduled Task: taegliches DB-Backup um 03:00 (laeuft als SYSTEM,
REM damit es config\.db-credentials lesen kann).
REM ============================================================
echo.
echo Registriere Scheduled Task fuer taegliches Backup (03:00)...
SET "BACKUP_BAT=%INSTALL_DIR%\backup.bat"
if not exist "%BACKUP_BAT%" (
    echo WARNUNG: backup.bat nicht gefunden unter %BACKUP_BAT% - Task nicht angelegt.
    goto :task_done
)

REM StartWhenAvailable (Log-Audit 2026-11-15 A13): war der PC um 03:00 aus,
REM fiel die Sicherung des Tages ersatzlos aus. Mit der Einstellung holt
REM Windows den Lauf nach dem Einschalten nach - schtasks /create kennt sie
REM nicht, deshalb Register-ScheduledTask. AllowStartIfOnBatteries: sonst
REM laeuft die Sicherung auf einem Notebook im Akkubetrieb nie. Pfade kommen
REM ueber Umgebungsvariablen in PowerShell, kein Quoting im Befehl.
REM Einzeiler weil caret-Continuation im if-Block unreliable ist
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $a = New-ScheduledTaskAction -Execute $env:BACKUP_BAT -WorkingDirectory $env:INSTALL_DIR; $t = New-ScheduledTaskTrigger -Daily -At '03:00'; $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; $p = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest; Register-ScheduledTask -TaskName 'PraxisZeit-Backup' -Action $a -Trigger $t -Settings $s -Principal $p -Force -ErrorAction Stop | Out-Null; exit 0 } catch { Write-Host $_; exit 1 }"
if not errorlevel 1 goto :task_ok
REM Rueckfall (z.B. ohne ScheduledTasks-Modul): wie bisher, ohne Nachholen.
echo WARNUNG: Register-ScheduledTask fehlgeschlagen - lege die Aufgabe per schtasks an.
schtasks /create /tn "PraxisZeit-Backup" /tr "\"%BACKUP_BAT%\"" /sc daily /st 03:00 /ru SYSTEM /f
if errorlevel 1 (
    echo WARNUNG: Scheduled Task konnte nicht angelegt werden.
    goto :task_done
)
:task_ok
echo Scheduled Task "PraxisZeit-Backup" aktiv.

:task_done

if not defined PRAXISZEIT_NONINTERACTIVE pause
