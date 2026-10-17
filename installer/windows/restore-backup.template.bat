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
REM
REM Gesamtreview 1.20: Das Backup wird VOR jeder Aenderung entpackt und auf
REM die Schlusszeile von pg_dump geprueft. Eingespielt wird zuerst in eine
REM Zwischendatenbank, psql bricht beim ersten Fehler ab. Erst danach ersetzt
REM sie die bisherige Datenbank. Scheitert ein Schritt, bleibt der Dienst aus
REM und das Script endet mit Exit-Code 1 - frueher startete es den Dienst
REM immer und meldete Erfolg, auch fuer eine halb eingespielte Datenbank.
REM Gegenstueck zu praxiszeit-server.py restore unter Linux und macOS.
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
SET "RESTORE_DB=praxiszeit_restore"
REM psql: -X ohne psqlrc, -w nie nach einem Passwort fragen, ON_ERROR_STOP
REM bricht beim ersten Fehler ab - ohne meldet psql trotz Fehlern Erfolg.
SET "PSQL_ARGS=-X -w -q -v ON_ERROR_STOP=1 -U praxiszeit -p 5432"
REM Die DROP-IF-EXISTS-Zeilen des Dumps melden in der frischen Datenbank je
REM Objekt einen NOTICE. Fehler zeigt psql weiter an.
SET "PGOPTIONS=-c client_min_messages=warning"

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

REM --- Schritt 1: Backup entpacken und pruefen - vor jeder Aenderung ---
REM Ein abgeschnittenes Archiv bricht beim Entpacken ab, ein abgebrochener
REM Dump hat keine Schlusszeile. pg_dump 18 haengt danach noch eine
REM unrestrict-Zeile an, deshalb die letzten 4 KB statt der letzten Zeile.
REM Ein Fehler erscheint als eine Zeile statt als Python-Traceback.
echo Entpacke und pruefe Backup...
"%PYTHON%" -c "import gzip,os,shutil,sys;sys.excepthook=lambda t,v,b:print(t.__name__+': '+str(v),file=sys.stderr);s,d=sys.argv[1:3];i=gzip.open(s,'rb');o=open(d,'wb');shutil.copyfileobj(i,o,1048576);o.close();i.close();f=open(d,'rb');f.seek(max(0,os.path.getsize(d)-4096));t=f.read();f.close();sys.exit(0 if b'PostgreSQL database dump complete' in t else 3)" "%BACKUP_GZ%" "%BACKUP_DUMP%"
if errorlevel 1 goto :backup_unbrauchbar
echo OK.
echo.

REM --- Schritt 2: Service stoppen ---
echo Stoppe PraxisZeit Service...
net stop PraxisZeit 2>nul
timeout /t 3 /nobreak >nul
echo.

REM --- Schritt 3: PostgreSQL starten ---
REM Laeuft PostgreSQL schon als eigener Dienst, meldet pg_ctl das nur - ob
REM der Server erreichbar ist, zeigt der erste psql-Aufruf.
echo Starte PostgreSQL...
"%PG_CTL%" -D "%PG_DATA%" -l "%DIR%\logs\pg-restore.log" start
timeout /t 5 /nobreak >nul
echo.

REM --- Schritt 4: in die Zwischendatenbank einspielen ---
REM Die bisherige Datenbank bleibt dabei unangetastet.
echo Spiele das Backup in die Zwischendatenbank %RESTORE_DB% ein...
"%PSQL%" %PSQL_ARGS% -d postgres -c "DROP DATABASE IF EXISTS %RESTORE_DB% WITH (FORCE)" -c "CREATE DATABASE %RESTORE_DB% OWNER praxiszeit ENCODING 'UTF8'"
if errorlevel 1 goto :bestand_unveraendert
"%PSQL%" %PSQL_ARGS% -d %RESTORE_DB% -f "%BACKUP_DUMP%"
if errorlevel 1 goto :bestand_unveraendert
REM Ohne alembic_version ist es kein PraxisZeit-Backup.
"%PSQL%" %PSQL_ARGS% -d %RESTORE_DB% -c "DO $$ BEGIN IF NOT EXISTS (SELECT FROM alembic_version) THEN RAISE EXCEPTION 'Tabelle alembic_version ist leer'; END IF; END $$"
if errorlevel 1 goto :kein_praxiszeit_backup
echo OK.
echo.

REM --- Schritt 5: bisherige Datenbank ersetzen ---
echo Ersetze die bisherige Datenbank...
"%PSQL%" %PSQL_ARGS% -d postgres -c "DROP DATABASE IF EXISTS praxiszeit WITH (FORCE)"
if errorlevel 1 goto :bestand_unveraendert
"%PSQL%" %PSQL_ARGS% -d postgres -c "ALTER DATABASE %RESTORE_DB% RENAME TO praxiszeit"
if errorlevel 1 goto :tausch_gescheitert
echo.

REM --- Schritt 6: Berechtigungen setzen ---
REM GRANT CONNECT gehoert zur Datenbank, nicht zu ihrem Inhalt - steht nicht im Dump.
echo Setze Berechtigungen...
"%PSQL%" %PSQL_ARGS% -d praxiszeit -f "%DIR%\app\backend\init-db-user.sql"
if errorlevel 1 goto :rechte_gescheitert
echo.

REM --- Schritt 7: PostgreSQL stoppen + Service starten ---
echo Stoppe PostgreSQL...
"%PG_CTL%" -D "%PG_DATA%" -m fast stop
timeout /t 3 /nobreak >nul
del "%BACKUP_DUMP%" 2>nul

echo Starte PraxisZeit Service...
net start PraxisZeit
if errorlevel 1 goto :dienst_startet_nicht

echo.
echo ==============================================
echo   Restore abgeschlossen!
echo ==============================================
echo Erst dieser Dienststart hebt ein Backup einer aelteren Version per
echo Migration auf den Stand dieser Installation - Ausgabe in logs\praxiszeit.log.
echo.
pause
exit /b 0

REM ============================================================
REM Fehlerpfade: Dienst bleibt aus, Exit-Code 1.
REM ============================================================

:backup_unbrauchbar
del "%BACKUP_DUMP%" 2>nul
echo.
echo FEHLER: Das Backup ist unvollstaendig oder kein lesbares gzip-Archiv -
echo die Schlusszeile von pg_dump fehlt, etwa weil die Kopie abgebrochen ist.
echo Es wurde nichts veraendert.
echo.
pause
exit /b 1

:kein_praxiszeit_backup
echo.
echo FEHLER: Das Backup enthaelt keine PraxisZeit-Datenbank - die Tabelle
echo alembic_version fehlt oder ist leer.
goto :bestand_unveraendert

:bestand_unveraendert
"%PSQL%" %PSQL_ARGS% -d postgres -c "DROP DATABASE IF EXISTS %RESTORE_DB% WITH (FORCE)" >nul 2>&1
"%PG_CTL%" -D "%PG_DATA%" -m fast stop >nul 2>&1
del "%BACKUP_DUMP%" 2>nul
echo.
echo FEHLER: Einspielen fehlgeschlagen - siehe Meldung oben.
echo Die bisherige Datenbank ist unveraendert. Der Dienst wurde NICHT gestartet;
echo nach Pruefung wieder starten mit: net start PraxisZeit
echo.
pause
exit /b 1

:tausch_gescheitert
"%PG_CTL%" -D "%PG_DATA%" -m fast stop >nul 2>&1
del "%BACKUP_DUMP%" 2>nul
echo.
echo FEHLER: Die bisherige Datenbank ist entfernt, die eingespielten Daten liegen
echo noch in der Zwischendatenbank %RESTORE_DB%. Den Dienst NICHT starten,
echo sondern restore-backup.bat mit derselben Datei erneut aufrufen.
echo.
pause
exit /b 1

:rechte_gescheitert
"%PG_CTL%" -D "%PG_DATA%" -m fast stop >nul 2>&1
del "%BACKUP_DUMP%" 2>nul
echo.
echo FEHLER: Backup eingespielt, aber die Rechte der Anwendungsrolle liessen sich
echo nicht setzen. Der Dienst wurde NICHT gestartet; restore-backup.bat mit
echo derselben Datei erneut aufrufen.
echo.
pause
exit /b 1

:dienst_startet_nicht
echo.
echo FEHLER: Backup eingespielt, aber der PraxisZeit-Dienst startet nicht.
echo Ursache in logs\service-stderr.log und logs\praxiszeit.log pruefen.
echo.
pause
exit /b 1
