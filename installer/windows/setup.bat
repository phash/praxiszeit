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
    pause
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
            --install_runtimes 0
        if not errorlevel 1 set "PG_INSTALL_RESULT=0"
    )

    if not "%PG_INSTALL_RESULT%"=="0" (
        echo.
        echo FEHLER: PostgreSQL-Installation fehlgeschlagen!
        echo Bitte installieren Sie PostgreSQL manuell von:
        echo   https://www.enterprisedb.com/downloads/postgres-postgresql-downloads
        pause
        exit /b 1
    )

    REM EDB erstellt einen eigenen Service und Datenverzeichnis mit User "postgres".
    REM PraxisZeit verwaltet PostgreSQL selbst mit eigenem Superuser "praxiszeit".
    REM Daher: EDB-Service und Datenverzeichnis entfernen.
    echo Raeume EDB-Installer auf...
    net stop PraxisZeit-PostgreSQL 2>nul
    sc delete PraxisZeit-PostgreSQL 2>nul
    if exist "%PG_DATA_DIR%\PG_VERSION" rd /s /q "%PG_DATA_DIR%"
    if not exist "%PG_DATA_DIR%" mkdir "%PG_DATA_DIR%"

    echo PostgreSQL installiert.
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
    pause
)

REM ============================================================
REM Schritt 2: Python Dependencies installieren
REM ============================================================

if not exist "%PYTHON%" (
    echo FEHLER: Python nicht gefunden: %PYTHON%
    pause
    exit /b 1
)

echo.
echo Konfiguriere Python...

REM Fix Python ._pth fuer pip/site-packages
if exist "%DIR%bin\python\fix-pth.py" (
    "%PYTHON%" "%DIR%bin\python\fix-pth.py"
)

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
    pause
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

pause
