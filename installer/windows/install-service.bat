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
"%NSSM%" set PraxisZeit AppRotateFiles 1
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

REM Einzeiler weil caret-Continuation im if-Block unreliable ist
schtasks /create /tn "PraxisZeit-Backup" /tr "\"%BACKUP_BAT%\"" /sc daily /st 03:00 /ru SYSTEM /f
if errorlevel 1 (
    echo WARNUNG: Scheduled Task konnte nicht angelegt werden.
) else (
    echo Scheduled Task "PraxisZeit-Backup" aktiv.
)

:task_done

if not defined PRAXISZEIT_NONINTERACTIVE pause
