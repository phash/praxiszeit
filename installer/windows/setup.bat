@echo off
setlocal DisableDelayedExpansion
REM ============================================================
REM PraxisZeit Setup fuer Windows
REM Installiert PostgreSQL (silent) + Python-Dependencies
REM Muss als Administrator ausgefuehrt werden!
REM ============================================================

echo.
echo ==============================================
echo   PraxisZeit Setup fuer Windows
echo ==============================================
echo.

SET "DIR=%~dp0"
SET "PYTHON=%DIR%bin\python\python.exe"
SET "PG_INSTALLER=%DIR%bin\postgresql-installer.exe"
SET "PG_INSTALL_DIR=%DIR%bin\postgresql"
SET "PG_DATA_DIR=%DIR%data\db"

REM --- Administratorrechte pruefen ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo FEHLER: Bitte als Administrator ausfuehren!
    echo Rechtsklick auf setup.bat ^> "Als Administrator ausfuehren"
    if not defined PRAXISZEIT_NONINTERACTIVE pause
    exit /b 1
)

REM --- Verzeichnisse erstellen ---
if not exist "%DIR%data\db" mkdir "%DIR%data\db"
if not exist "%DIR%data\backups" mkdir "%DIR%data\backups"
if not exist "%DIR%config\ssl" mkdir "%DIR%config\ssl"
if not exist "%DIR%logs" mkdir "%DIR%logs"

REM ============================================================
REM Schritt 1: PostgreSQL installieren (silent)
REM ============================================================

REM --- System-PostgreSQL erkennen und ggf. wiederverwenden ---
REM Wenn eine kompatible Version (>= 16) bereits auf dem System installiert
REM ist, legen wir eine Junction auf ihr Basisverzeichnis an und ueberspringen
REM die EDB-Installation. Bei aelteren Versionen wird der Installer zur
REM Aktualisierung ausgefuehrt (der EDB-Installer installiert die neue Version
REM parallel in unser Bundle-Verzeichnis).
if exist "%PG_INSTALL_DIR%\bin\pg_ctl.exe" goto :pg_detect_done

call :detect_system_pg
REM Default setzen, damit die Parse-Time-Expansion in der Block-Syntax unten
REM keine leeren Tokens erzeugt (Syntax-Fehler bei "if  GEQ 16").
if not defined SYSTEM_PG_MAJOR set "SYSTEM_PG_MAJOR=0"
if defined SYSTEM_PG_BASE (
    echo.
    echo System-PostgreSQL gefunden: %SYSTEM_PG_BASE%
    echo Version: PostgreSQL %SYSTEM_PG_MAJOR%
    if %SYSTEM_PG_MAJOR% GEQ 16 (
        echo Kompatible Version - verlinke System-PostgreSQL in das Bundle-Verzeichnis...
        REM Eventuell vorhandenes leeres Bundle-Verzeichnis entfernen
        if exist "%PG_INSTALL_DIR%" rd "%PG_INSTALL_DIR%" 2>nul
        if exist "%PG_INSTALL_DIR%" rd /s /q "%PG_INSTALL_DIR%" 2>nul
        mklink /J "%PG_INSTALL_DIR%" "%SYSTEM_PG_BASE%" >nul
        if not errorlevel 1 (
            echo System-PostgreSQL verlinkt, Installer uebersprungen.
            goto :pg_detect_done
        )
        echo WARNUNG: Junction fehlgeschlagen, kopiere Binaries ^(dauert etwas^)...
        xcopy "%SYSTEM_PG_BASE%" "%PG_INSTALL_DIR%" /E /I /Q /Y >nul
        if exist "%PG_INSTALL_DIR%\bin\pg_ctl.exe" goto :pg_detect_done
        echo WARNUNG: Kopieren fehlgeschlagen, fahre mit EDB-Installer fort.
    ) else (
        echo Version ^(%SYSTEM_PG_MAJOR%^) nicht kompatibel - fuehre Installation aus.
    )
)
:pg_detect_done

if exist "%PG_INSTALL_DIR%\bin\pg_ctl.exe" (
    echo PostgreSQL bereits installiert, ueberspringe...
) else if exist "%PG_INSTALLER%" (
    echo.
    echo Installiere PostgreSQL ^(kann einige Minuten dauern^)...
    echo.
    REM F-025: Generate a random one-shot password for the EDB installer.
    REM The EDB-installed PostgreSQL service + data directory are removed
    REM immediately below; praxiszeit-server.py later runs initdb with its
    REM own secrets.token_hex(32)-generated credentials in .db-credentials.
    REM This password only has to live as long as the EDB installer itself.
    REM PowerShell is used because DisableDelayedExpansion forbids the usual
    REM setlocal-EnableDelayedExpansion pattern; the for-loop scope keeps the
    REM value out of the environment after the installer call.
    set "PG_INSTALL_RESULT=1"
    REM --install_runtimes 1: der EDB-Installer installiert die Microsoft Visual
    REM C++ Runtime vcruntime140*.dll, gegen die die PG-18-Binaries gelinkt sind.
    REM Frueher stand hier 0 -> auf frischem Windows OHNE vorhandenen VC++-Redist
    REM schlug initdb.exe sofort mit Exit 3221225781 = 0xC0000135 STATUS_DLL_NOT_FOUND
    REM fehl und der Dienst loopte endlos. Feldreport 2026-05-26. Der Redist-Install
    REM ist idempotent und systemweit.
    REM Hinweis: keine Klammern in diesen REM-Zeilen - unbalancierte Klammern in
    REM einem ()-Block beenden den Block vorzeitig.
    for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "-join ((48..57)+(65..90)+(97..122)|Get-Random -Count 32|ForEach-Object {[char]$_})"`) do (
        "%PG_INSTALLER%" ^
            --mode unattended ^
            --unattendedmodeui none ^
            --prefix "%PG_INSTALL_DIR%" ^
            --datadir "%PG_DATA_DIR%" ^
            --superpassword "%%P" ^
            --serverport 5432 ^
            --disable-components stackbuilder,pgAdmin ^
            --servicename "PraxisZeit-PostgreSQL" ^
            --install_runtimes 1
    )
    REM #286: Der EDB-Unattended-Installer kehrt teils mit Nicht-0-Exitcode zurueck
    REM bzw. legt die Binaries ASYNCHRON ab - sie erscheinen erst Minuten spaeter.
    REM Erfolg daher an der Existenz von pg_ctl.exe festmachen, nicht am Exitcode,
    REM und bis zu 6 Minuten darauf warten. CRLF-Zeilenenden noetig: mit LF brechen
    REM cmd.exe-Label-Spruenge call/goto :label und mehrzeilige Klammer-Bloecke.
    REM Hinweis: keine Klammern in diesen REM-Zeilen - dies ist noch ein ()-Block.
    echo Warte auf PostgreSQL-Binaries ^(kann einige Minuten dauern^)...
    for /l %%w in (1,1,72) do if not exist "%PG_INSTALL_DIR%\bin\pg_ctl.exe" timeout /t 5 /nobreak >nul

    if exist "%PG_INSTALL_DIR%\bin\pg_ctl.exe" (
        REM Binaries vorhanden = EDB-Installer fertig -> dessen eigenen Dienst und
        REM Datenverzeichnis entfernen. PraxisZeit verwaltet PG mit eigenem Cluster.
        REM Kein Race mit dem Installer, weil die Binaries bereits geschrieben sind.
        echo Raeume EDB-Installer auf...
        net stop PraxisZeit-PostgreSQL 2>nul
        sc delete PraxisZeit-PostgreSQL 2>nul
        if exist "%PG_DATA_DIR%\PG_VERSION" rd /s /q "%PG_DATA_DIR%"
        if not exist "%PG_DATA_DIR%" mkdir "%PG_DATA_DIR%"
        echo PostgreSQL installiert.
    ) else (
        REM Binaries noch nicht da ist KEIN harter Fehler: der Dienst initialisiert
        REM PostgreSQL beim ersten Start selbst und legt ein fremdes EDB-Datadir
        REM dabei sauber zur Seite. Kein exit/b - sonst bricht das Setup grundlos ab.
        echo HINWEIS: PostgreSQL-Binaries noch nicht sichtbar. Der Dienst
        echo initialisiert die Datenbank beim ersten Start. Setup faehrt fort.
    )
) else (
    echo.
    echo WARNUNG: PostgreSQL-Installer nicht gefunden.
    echo.
    echo Bitte installieren Sie PostgreSQL manuell:
    echo   https://www.enterprisedb.com/downloads/postgres-postgresql-downloads
    echo.
    echo Nach der Installation: pg_ctl.exe muss unter
    echo   %PG_INSTALL_DIR%\bin\pg_ctl.exe
    echo erreichbar sein.
    echo.
    if not defined PRAXISZEIT_NONINTERACTIVE pause
)

REM ============================================================
REM Schritt 2: Python Dependencies installieren
REM ============================================================

if not exist "%PYTHON%" (
    echo FEHLER: Python nicht gefunden: %PYTHON%
    if not defined PRAXISZEIT_NONINTERACTIVE pause
    exit /b 1
)

echo.
echo Konfiguriere Python...

REM Fix Python ._pth fuer pip/site-packages
if exist "%DIR%bin\python\fix-pth.py" (
    "%PYTHON%" "%DIR%bin\python\fix-pth.py"
)

REM PYTHONNOUSERSITE: das gebuendelte Python (Version-passend zu einem evtl.
REM auf dem Rechner installierten System-Python) wuerde sonst dessen
REM User-Site (%APPDATA%\Python\PythonXY\site-packages) sehen. pip wertet dort
REM bereits vorhandene Pakete als "erfuellt" und installiert NICHTS ins Bundle
REM -> der als LocalSystem laufende Dienst (ohne dieses User-Site) findet die
REM Dependencies dann nicht. Mit PYTHONNOUSERSITE=1 installiert pip garantiert
REM ins gebuendelte site-packages.
set "PYTHONNOUSERSITE=1"

echo Installiere pip...
if exist "%DIR%bin\python\get-pip.py" (
    "%PYTHON%" "%DIR%bin\python\get-pip.py" --quiet 2>nul
)

echo Installiere Python-Abhaengigkeiten (kann einige Minuten dauern)...
"%PYTHON%" -m pip install --quiet -r "%DIR%app\backend\requirements.txt"

if %errorlevel% neq 0 (
    echo.
    echo FEHLER: Python-Abhaengigkeiten konnten nicht installiert werden.
    echo Stellen Sie sicher, dass eine Internetverbindung besteht.
    if not defined PRAXISZEIT_NONINTERACTIVE pause
    exit /b 1
)

REM Verifizieren, dass die Kern-Module wirklich importierbar sind. Die Deps sind
REM im Release bereits vorgebuendelt (build-release.sh); dieser Check faengt einen
REM kaputten Zustand sichtbar ab, BEVOR der Dienst startet (statt spaeter still an
REM der Migration zu scheitern -> ERR_CONNECTION_REFUSED). -s = User-Site ignorieren.
"%PYTHON%" -s -c "import alembic, uvicorn, fastapi, sqlalchemy, psycopg2" 2>nul
if %errorlevel% neq 0 (
    echo.
    echo FEHLER: Python-Abhaengigkeiten fehlen im Bundle ^(Import-Check fehlgeschlagen^).
    echo Internetverbindung pruefen und Setup erneut ausfuehren.
    if not defined PRAXISZEIT_NONINTERACTIVE pause
    exit /b 1
)

REM ============================================================
REM Schritt 3: Konfiguration
REM ============================================================

if not exist "%DIR%config\praxiszeit.conf" (
    if exist "%DIR%config\praxiszeit.conf.example" (
        echo.
        echo Erstelle Konfigurationsdatei...
        copy "%DIR%config\praxiszeit.conf.example" "%DIR%config\praxiszeit.conf" >nul
        echo.
        echo WICHTIG: Bitte passen Sie die Konfiguration an:
        echo   %DIR%config\praxiszeit.conf
        echo.
        echo Mindestens aendern:
        echo   - [practice] name = "Ihre Praxis"
        echo   - [admin] email = "ihre@email.de"
        echo   - [admin] password = "IhrSicheresPasswort"
        echo.
    )
) else (
    echo Konfiguration vorhanden.
)

REM ============================================================
REM Fertig
REM ============================================================

echo.
echo ==============================================
echo   Setup abgeschlossen!
echo ==============================================
echo.
echo Naechste Schritte:
echo   1. Konfiguration anpassen: config\praxiszeit.conf
echo   2. Service installieren:   install-service.bat
echo   3. Service starten:        net start PraxisZeit
echo.

if not defined PRAXISZEIT_NONINTERACTIVE pause
goto :eof

REM ============================================================
REM Subroutinen
REM ============================================================

:detect_system_pg
REM Sucht eine systemweit installierte PostgreSQL-Version.
REM Setzt bei Erfolg die globalen Variablen SYSTEM_PG_BASE und SYSTEM_PG_MAJOR.
set "SYSTEM_PG_BASE="
set "SYSTEM_PG_MAJOR="

REM 1. Registry-Eintraege pruefen (EDB-Installer legt diese an)
REM Format: "    Base Directory    REG_SZ    C:\Program Files\PostgreSQL\18"
REM tokens=1-3,* : %%a=Base %%b=Directory %%c=REG_SZ %%d=Pfad (inkl. Spaces)
for /f "tokens=1-3,*" %%a in ('reg query "HKLM\SOFTWARE\PostgreSQL\Installations" /s /v "Base Directory" 2^>nul ^| findstr /C:"Base Directory"') do (
    if exist "%%d\bin\pg_ctl.exe" set "SYSTEM_PG_BASE=%%d"
)

REM 2. Fallback: haeufige Installationspfade (neueste Version zuerst)
if not defined SYSTEM_PG_BASE if exist "%ProgramFiles%\PostgreSQL\18\bin\pg_ctl.exe" set "SYSTEM_PG_BASE=%ProgramFiles%\PostgreSQL\18"
if not defined SYSTEM_PG_BASE if exist "%ProgramFiles%\PostgreSQL\17\bin\pg_ctl.exe" set "SYSTEM_PG_BASE=%ProgramFiles%\PostgreSQL\17"
if not defined SYSTEM_PG_BASE if exist "%ProgramFiles%\PostgreSQL\16\bin\pg_ctl.exe" set "SYSTEM_PG_BASE=%ProgramFiles%\PostgreSQL\16"
if not defined SYSTEM_PG_BASE if exist "%ProgramFiles%\PostgreSQL\15\bin\pg_ctl.exe" set "SYSTEM_PG_BASE=%ProgramFiles%\PostgreSQL\15"
if not defined SYSTEM_PG_BASE if exist "%ProgramFiles%\PostgreSQL\14\bin\pg_ctl.exe" set "SYSTEM_PG_BASE=%ProgramFiles%\PostgreSQL\14"

if not defined SYSTEM_PG_BASE goto :eof

REM Major-Version auslesen (pg_ctl --version: "pg_ctl (PostgreSQL) 18.3")
pushd "%SYSTEM_PG_BASE%\bin"
for /f "tokens=3" %%v in ('pg_ctl.exe --version 2^>nul') do call :_parse_pg_major %%v
popd
goto :eof

:_parse_pg_major
for /f "tokens=1 delims=." %%m in ("%~1") do set "SYSTEM_PG_MAJOR=%%m"
goto :eof
