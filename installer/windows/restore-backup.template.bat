@echo off
setlocal DisableDelayedExpansion

REM ============================================================
REM PraxisZeit Backup Restore Template
REM
REM Usage: restore-backup.bat <backup-file.sql.gz>
REM
REM F-025: No hardcoded passwords. Credentials are read from
REM config\.db-credentials which is created by praxiszeit-server.py on
REM first run with restricted file-system permissions.
REM
REM Edit INSTALL_DIR below to match your installation path, or pass it
REM via the PRAXISZEIT_INSTALL_DIR environment variable.
REM ============================================================

echo.
echo ==============================================
echo   PraxisZeit Backup Restore
echo ==============================================
echo.

if "%~1"=="" (
    echo Usage: %~nx0 ^<backup-file.sql.gz^>
    echo.
    echo Example: %~nx0 C:\Backup\praxiszeit_20260411_120000.sql.gz
    pause
    exit /b 1
)

SET "BACKUP_GZ=%~1"
if not exist "%BACKUP_GZ%" (
    echo FEHLER: Backup-Datei nicht gefunden:
    echo   %BACKUP_GZ%
    pause
    exit /b 1
)

REM Installation directory (edit if non-default)
if defined PRAXISZEIT_INSTALL_DIR (
    SET "DIR=%PRAXISZEIT_INSTALL_DIR%"
) else (
    SET "DIR=C:\praxiszeit"
)

SET "BACKUP_DUMP=%TEMP%\praxiszeit-restore.sql"
SET "PYTHON=%DIR%\bin\python\python.exe"
SET "PSQL=%DIR%\bin\postgresql\bin\psql.exe"
SET "PG_CTL=%DIR%\bin\postgresql\bin\pg_ctl.exe"
SET "PG_DATA=%DIR%\data\db"

REM --- Credentials laden (F-025: kein Fallback) ---
SET "CREDS_FILE=%DIR%\config\.db-credentials"
if not exist "%CREDS_FILE%" (
    echo FEHLER: Credentials-Datei fehlt: %CREDS_FILE%
    echo Die Anwendung muss mindestens einmal gestartet worden sein.
    pause
    exit /b 1
)
for /f "tokens=1,* delims==" %%a in (%CREDS_FILE%) do (
    if "%%a"=="SUPERUSER_PASSWORD" SET "PGPASSWORD=%%b"
)
if not defined PGPASSWORD (
    echo FEHLER: SUPERUSER_PASSWORD fehlt in %CREDS_FILE%.
    pause
    exit /b 1
)

REM --- Explizite Bestaetigung (destruktiv!) ---
echo.
echo WARNUNG: Dies LOESCHT die aktuelle Datenbank und stellt das Backup wieder her.
echo Backup: %BACKUP_GZ%
echo.
set /p CONFIRM="Zum Bestaetigen 'LOESCHEN' eingeben: "
if /i not "%CONFIRM%"=="LOESCHEN" (
    echo Abgebrochen.
    pause
    exit /b 0
)

REM --- Schritt 1: Service stoppen ---
echo Stoppe PraxisZeit Service...
net stop PraxisZeit 2>nul
timeout /t 3 /nobreak >nul
echo.

REM --- Schritt 2: PostgreSQL starten ---
echo Starte PostgreSQL...
"%PG_CTL%" -D "%PG_DATA%" -l "%DIR%\logs\pg-restore.log" start
timeout /t 5 /nobreak >nul
echo.

REM --- Schritt 3: Backup entpacken ---
echo Entpacke Backup...
"%PYTHON%" -c "import gzip,shutil;shutil.copyfileobj(gzip.open(r'%BACKUP_GZ%','rb'),open(r'%BACKUP_DUMP%','wb'))"
if not exist "%BACKUP_DUMP%" (
    echo FEHLER: Entpacken fehlgeschlagen.
    "%PG_CTL%" -D "%PG_DATA%" -m fast stop
    pause
    exit /b 1
)
echo OK.
echo.

REM --- Schritt 4: Datenbank droppen + neu anlegen ---
echo Loesche alte Datenbank...
"%PSQL%" -U praxiszeit -p 5432 -c "DROP DATABASE IF EXISTS praxiszeit;"
echo Erstelle neue Datenbank...
"%PSQL%" -U praxiszeit -p 5432 -c "CREATE DATABASE praxiszeit OWNER praxiszeit ENCODING 'UTF8';"
echo.

REM --- Schritt 5: Restore ---
echo Stelle Backup wieder her...
"%PSQL%" -U praxiszeit -d praxiszeit -p 5432 -f "%BACKUP_DUMP%"
echo.

REM --- Schritt 6: Berechtigungen setzen ---
echo Setze Berechtigungen...
"%PSQL%" -U praxiszeit -d praxiszeit -p 5432 -f "%DIR%\app\backend\init-db-user.sql"
echo.

REM --- Schritt 7: PostgreSQL stoppen + Service starten ---
echo Stoppe PostgreSQL...
"%PG_CTL%" -D "%PG_DATA%" -m fast stop
timeout /t 3 /nobreak >nul

echo Starte PraxisZeit Service...
net start PraxisZeit
echo.

REM --- Schritt 8: Aufraeumen ---
echo Raeume auf...
del "%BACKUP_DUMP%" 2>nul

echo.
echo ==============================================
echo   Restore abgeschlossen!
echo ==============================================
echo.

pause
