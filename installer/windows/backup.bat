@echo off
setlocal DisableDelayedExpansion
REM ============================================================
REM PraxisZeit Database Backup
REM Manueller Aufruf oder via Scheduled Task (taeglich 03:00)
REM Muss als SYSTEM oder mit Leserechten auf config\.db-credentials
REM laufen (siehe icacls-Hinweis in NATIVE-WINDOWS-PITFALLS.md).
REM ============================================================

SET "DIR=%~dp0"
SET "PYTHON=%DIR%bin\python\python.exe"
SET "SERVER=%DIR%praxiszeit-server.py"
SET "LOGFILE=%DIR%logs\backup.log"

if not exist "%PYTHON%" (
    echo [%date% %time%] ERROR: Python nicht gefunden: %PYTHON% >> "%LOGFILE%"
    exit /b 1
)

if not exist "%SERVER%" (
    echo [%date% %time%] ERROR: praxiszeit-server.py nicht gefunden: %SERVER% >> "%LOGFILE%"
    exit /b 1
)

REM Adminrechte pruefen (Log-Audit 2026-11-15 A19): ein Doppelklick ohne
REM "Als Administrator ausfuehren" endete in einem rohen PermissionError-
REM Traceback, weil config\.db-credentials nur fuer SYSTEM und Administratoren
REM lesbar ist. Die naechtliche Aufgabe laeuft als SYSTEM und besteht die
REM Pruefung. fltmc als zweite Probe: net session scheitert auch mit
REM Adminrechten, wenn der Dienst "Server" (LanmanServer) deaktiviert ist.
net session >nul 2>&1
if not errorlevel 1 goto :admin_ok
fltmc >nul 2>&1
if not errorlevel 1 goto :admin_ok
echo.
echo FEHLER: Die Sicherung braucht Administratorrechte.
echo Bitte backup.bat mit Rechtsklick - "Als Administrator ausfuehren" starten.
echo [%date% %time%] ERROR: ohne Administratorrechte gestartet - keine Sicherung >> "%LOGFILE%" 2>nul
exit /b 1
:admin_ok

REM UTF-8 erzwingen (Fallstrick cp1252 bei Emojis in Logs)
SET "PYTHONUTF8=1"

echo [%date% %time%] Starte Backup >> "%LOGFILE%"
"%PYTHON%" "%SERVER%" backup >> "%LOGFILE%" 2>&1
set "RC=%errorlevel%"
echo [%date% %time%] Backup beendet, Exit-Code %RC% >> "%LOGFILE%"

exit /b %RC%
