@echo off
setlocal DisableDelayedExpansion
REM ============================================================
REM PraxisZeit Vollstaendige Deinstallation
REM Erstellt ein DB-Backup, entfernt Services und alle Dateien
REM Muss als Administrator ausgefuehrt werden!
REM ============================================================

echo.
echo ==============================================
echo   PraxisZeit Deinstallation
echo ==============================================
echo.

SET "DIR=%~dp0."
SET "PSQL=%DIR%\bin\postgresql\bin\psql.exe"
SET "PG_DUMP=%DIR%\bin\postgresql\bin\pg_dump.exe"
SET "PG_CTL=%DIR%\bin\postgresql\bin\pg_ctl.exe"
SET "PG_DATA=%DIR%\data\db"
SET "NSSM=%DIR%\nssm.exe"
SET "BACKUP_DIR=%USERPROFILE%\Desktop"
REM psql/pg_dump sprechen TCP mit localhost: Passwort nur per SCRAM (S3-07).
SET "PGREQUIREAUTH=scram-sha-256"
REM Datenbank-Port aus config\praxiszeit.conf, Standard 5432. Scheitert Python,
REM bleibt es bei 5432 - die Deinstallation darf daran nicht abbrechen.
SET "DB_PORT="
if exist "%DIR%\bin\python\python.exe" if exist "%DIR%\praxiszeit-server.py" (
    for /f "usebackq delims=" %%p in (`""%DIR%\bin\python\python.exe" "%DIR%\praxiszeit-server.py" print-db-port 2>nul"`) do SET "DB_PORT=%%p"
)
SET "DB_PORT_FALLBACK="
if not defined DB_PORT (
    SET "DB_PORT=5432"
    SET "DB_PORT_FALLBACK=1"
)

REM --- Administratorrechte: bei Bedarf selbst elevieren ---
REM Apps & Features startet die UninstallString u.U. OHNE Elevation; wir starten
REM uns dann per UAC-Prompt neu, damit Dienste/Registry/Dateien entfernt werden koennen.
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Fordere Administrator-Rechte an...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo WARNUNG: Dies entfernt PraxisZeit vollstaendig!
echo Ein Datenbank-Backup wird auf dem Desktop gespeichert.
echo.
set /p CONFIRM="Fortfahren? (j/n): "
if /i not "%CONFIRM%"=="j" goto :keep_failed
echo.
echo FEHLER: Die automatischen Sicherungen aus %DIR%\data\backups liessen
echo sich nicht nach %KEEP_DIR% verschieben. Das Installationsverzeichnis wird
echo NICHT entfernt - bitte den Ordner data\backups von Hand sichern und
echo %DIR% danach selbst loeschen.
pause
exit /b 1

:cancelled

REM ============================================================
REM Schritt 1: Datenbank-Backup
REM ============================================================

echo.
echo Erstelle Datenbank-Backup...

REM Credentials laden
SET "CREDS_FILE=%DIR%\config\.db-credentials"
if exist "%CREDS_FILE%" (
    REM usebackq + Anfuehrungszeichen: Pfade mit Leerzeichen (S3-09).
    for /f "usebackq tokens=1,* delims==" %%a in ("%CREDS_FILE%") do (
        if "%%a"=="SUPERUSER_PASSWORD" SET "PGPASSWORD=%%b"
    )
)

REM F-025: no fallback to a hardcoded password. If the credentials file is
REM missing the DB is either uninitialized or corrupted — abort the backup
REM step and let the user decide.
if not defined PGPASSWORD (
    echo WARNUNG: %CREDS_FILE% fehlt oder enthaelt kein SUPERUSER_PASSWORD.
    echo Ohne Credentials kann kein Backup erstellt werden.
    set /p CONT="Trotzdem OHNE Backup deinstallieren? (j/n): "
    if /i not "%CONT%"=="j" goto :cancelled
    goto :remove_services
)

REM Pruefen ob PostgreSQL laeuft, ggf. starten
"%PG_CTL%" -D "%PG_DATA%" status >nul 2>&1
if %errorlevel% neq 0 (
    echo Starte PostgreSQL fuer Backup...
    "%PG_CTL%" -D "%PG_DATA%" -l "%DIR%\logs\pg-uninstall.log" start >nul 2>&1
    timeout /t 5 /nobreak >nul
)

SET "BACKUP_FILE=%BACKUP_DIR%\praxiszeit-backup-%date:~6,4%%date:~3,2%%date:~0,2%.sql"
SET "DUMP_LOG=%TEMP%\praxiszeit-uninstall-dump.log"

REM -w PFLICHT: ohne haengt pg_dump headless an der Passwort-Abfrage. Der
REM PraxisZeit-Cluster hat KEINEN postgres-Superuser -> der fruehere Fallback
REM haette nur gehangen, daher entfernt.
REM Audit 2026-11-07 S3-02: frueher genuegte "Datei existiert" - ein
REM abgebrochener Dump (Desktop voll, Verbindung weg) hinterliess eine halbe
REM .sql-Datei, die als "Backup gespeichert" galt, danach wurden alle Daten
REM geloescht. Jetzt zaehlen nur Exit-Code 0 UND die Schlusszeile von pg_dump.
"%PG_DUMP%" -w -h localhost -p %DB_PORT% -U praxiszeit -d praxiszeit -f "%BACKUP_FILE%" 2>"%DUMP_LOG%"
if errorlevel 1 goto :backup_failed
if not exist "%BACKUP_FILE%" goto :backup_failed
findstr /c:"PostgreSQL database dump complete" "%BACKUP_FILE%" >nul 2>&1
if errorlevel 1 goto :backup_failed
del "%DUMP_LOG%" 2>nul
goto :backup_ok

:backup_failed
del "%BACKUP_FILE%" 2>nul
echo.
echo FEHLER: Das Datenbank-Backup ist fehlgeschlagen oder unvollstaendig.
if exist "%DUMP_LOG%" type "%DUMP_LOG%"
del "%DUMP_LOG%" 2>nul
if defined DB_PORT_FALLBACK echo Hinweis: Der Datenbank-Port aus config\praxiszeit.conf war nicht lesbar, versucht wurde 5432.
echo Es wurde nichts geloescht. Bitte die Ursache beheben ^(z. B. Platz auf dem
echo Desktop^) und die Deinstallation erneut starten.
set /p CONT="Trotzdem OHNE neues Backup deinstallieren? (j/n): "
if /i not "%CONT%"=="j" goto :cancelled
goto :remove_services

:backup_ok
echo Backup gespeichert: %BACKUP_FILE%

REM ============================================================
REM Schritt 2: Services stoppen und entfernen
REM ============================================================

:remove_services
echo.
echo Stoppe Services...
net stop PraxisZeit 2>nul
net stop PraxisZeit-PostgreSQL 2>nul

echo Entferne Scheduled Backup Task...
schtasks /delete /tn "PraxisZeit-Backup" /f 2>nul

echo Entferne PraxisZeit Service...
if exist "%NSSM%" (
    "%NSSM%" remove PraxisZeit confirm 2>nul
) else (
    sc delete PraxisZeit 2>nul
)
sc delete PraxisZeit-PostgreSQL 2>nul

REM ============================================================
REM Schritt 3: PostgreSQL stoppen
REM ============================================================

echo Stoppe PostgreSQL...
"%PG_CTL%" -D "%PG_DATA%" -m fast stop 2>nul
timeout /t 3 /nobreak >nul

REM ============================================================
REM Schritt 4: Firewall-Regel entfernen
REM ============================================================

echo Entferne Firewall-Regel...
netsh advfirewall firewall delete rule name="PraxisZeit" 2>nul

REM ============================================================
REM Schritt 4b: Apps-und-Features-Eintrag + Verknuepfungen entfernen
REM ============================================================
echo Entferne Apps-und-Features-Eintrag + Verknuepfungen...
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PraxisZeit" /f 2>nul
del "%PUBLIC%\Desktop\PraxisZeit.url" 2>nul
del "%ProgramData%\Microsoft\Windows\Start Menu\Programs\PraxisZeit.url" 2>nul

REM ============================================================
REM Schritt 5: Installationsverzeichnis entfernen
REM ============================================================

REM --- Automatische Sicherungen nie mitloeschen (S3-02) ---
REM data\backups enthaelt die naechtlichen Sicherungen (Aufbewahrung nach
REM Paragraf 16 Abs. 2 ArbZG). Sie wandern auf den Desktop; erst wenn das
REM geklappt hat, wird das Installationsverzeichnis entfernt.
SET "KEEP_DIR=%BACKUP_DIR%\PraxisZeit-Sicherungen-%date:~6,4%%date:~3,2%%date:~0,2%"
if exist "%DIR%\data\backups\*" (
    echo Verschiebe die automatischen Sicherungen nach %KEEP_DIR% ...
    robocopy "%DIR%\data\backups" "%KEEP_DIR%" /E /MOVE /NFL /NDL /NJH /NJS /NP >nul
    if errorlevel 8 goto :keep_failed
    echo Sicherungen liegen in: %KEEP_DIR%
)

echo.
echo Entferne Installationsverzeichnis: %DIR%

SET "CLEANUP_BAT=%TEMP%\praxiszeit-cleanup.bat"
echo @echo off > "%CLEANUP_BAT%"
echo timeout /t 2 /nobreak ^>nul >> "%CLEANUP_BAT%"
echo rd /s /q "%DIR%" >> "%CLEANUP_BAT%"
echo del "%%~f0" >> "%CLEANUP_BAT%"

echo.
echo ==============================================
echo   Deinstallation abgeschlossen!
echo ==============================================
echo.
if exist "%BACKUP_FILE%" echo Backup: %BACKUP_FILE%
echo.
echo Das Installationsverzeichnis wird nach Schliessen
echo dieses Fensters entfernt.
echo.
pause
start /b "" cmd /c "%CLEANUP_BAT%"
exit

:cancelled
echo Abgebrochen.
pause
exit /b 0
