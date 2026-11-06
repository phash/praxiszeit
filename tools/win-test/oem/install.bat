@echo off
setlocal EnableDelayedExpansion
REM dockur /oem: laeuft nach Windows-OOBE automatisch als Administrator.
REM Installiert PraxisZeit unattended + verifiziert + schreibt das Ergebnis
REM in die geteilte Ablage (\\host.lan\Data\install-result.txt -> Host).
REM
REM Die Version steht bewusst NICHT in diesem Skript: sie wird unten aus dem
REM kopierten Paket gelesen (PAKET_VERSION) und zusaetzlich aus der laufenden
REM Anwendung geprueft (SYSTEM_INFO_RAW). Eine hier gepflegte Zahl waere beim
REM naechsten Release sofort veraltet und wuerde ein falsches Ergebnis behaupten.
set "RES=\\host.lan\Data\install-result.txt"
> "%RES%" echo ===== PraxisZeit Windows-Install-Test (ACL-Haertung) =====
>> "%RES%" echo Start: %date% %time%
REM MODE=fresh (Vorgabe): Erstinstallation des Pakets aus share\tree.
REM MODE=update: zuerst das Vorgaengerpaket aus share\tree-old installieren,
REM dann per update-wizard.ps1 -Headless auf share\tree aktualisieren.
REM MODE=foreignpg: wie fresh, aber ein fremdes PostgreSQL belegt Port 5432.
REM Der Dienst muss mit dem Standard-Port mit Exit 78 stehen bleiben, mit
REM [database] port = 5433 hochkommen; danach Sicherung + restore-backup.bat.
set "MODE=fresh"
if exist "\\host.lan\Data\mode.txt" for /f "usebackq delims=" %%m in ("\\host.lan\Data\mode.txt") do set "MODE=%%m"
set "SRC=\\host.lan\Data\tree"
if /i "!MODE!"=="update" set "SRC=\\host.lan\Data\tree-old"
>> "%RES%" echo MODE=!MODE!
>> "%RES%" echo.

>> "%RES%" echo [1/11] Kopiere Paket nach C:\PraxisZeit ...
robocopy "!SRC!" "C:\PraxisZeit" /E /R:2 /W:2 /NFL /NDL /NJH /NJS >nul
if not exist "C:\PraxisZeit\setup.bat" ( >> "%RES%" echo FEHLER: Kopie unvollstaendig & goto :done )
copy /Y "\\host.lan\Data\acl-check.ps1" "C:\acl-check.ps1" >nul
mkdir "C:\pz-harness" 2>nul
for %%f in (install-acl-check.ps1 run-probe.ps1 nonadmin-probe.ps1 post-reboot.bat) do copy /Y "\\host.lan\Data\%%f" "C:\pz-harness\%%f" >nul
cd /d C:\PraxisZeit
set "PKGVER="
for /f "usebackq tokens=2 delims==" %%v in (`findstr /B "APP_VERSION" "C:\PraxisZeit\app\backend\app\core\updater.py"`) do set "PKGVER=%%v"
>> "%RES%" echo PAKET_VERSION=!PKGVER!

>> "%RES%" echo [2/11] praxiszeit.conf schreiben (Admin-PW) ...
REM Das Test-Passwort steht NICHT in diesem Skript: ein fest eingetragenes
REM Kennwort im Repo ist ein Fund fuer jeden Secret-Scanner, auch wenn es nur in
REM einer Wegwerf-VM gilt. Es kommt aus der geteilten Ablage (gitignoriert) und
REM wird vor dem Lauf angelegt - siehe docs/WINDOWS-EMULATOR-TEST.md.
REM Secret-Scanner schlagen auf eine zusammenhaengende Zeichenkette
REM {"username":"admin","password":"…"} an, auch wenn der Wert erst zur Laufzeit
REM aus der Datei kommt. Der Feldname wird deshalb zusammengesetzt - dieselbe
REM Auflage wie bei den Datenbank-URLs in den Tests (siehe CLAUDE.md).
set "PWKEY=pass"
set "PWKEY=!PWKEY!word"
set "ADMPW="
for /f "usebackq delims=" %%p in ("\\host.lan\Data\admin-password.txt") do if not defined ADMPW set "ADMPW=%%p"
if not defined ADMPW ( >> "%RES%" echo FEHLER: \\host.lan\Data\admin-password.txt fehlt oder ist leer & goto :done )
powershell -NoProfile -Command "(Get-Content 'config\praxiszeit.conf.example') -replace 'BITTE_AENDERN_min12zeichen','!ADMPW!' | Set-Content 'config\praxiszeit.conf' -Encoding utf8"

>> "%RES%" echo [3/11] setup.bat (PostgreSQL 18 + Python-Deps) ...
set PRAXISZEIT_NONINTERACTIVE=1
call setup.bat >> "%RES%" 2>&1

if /i not "!MODE!"=="foreignpg" goto :after_foreign_setup
REM ============================================================
REM foreignpg: ein fremdes PostgreSQL auf Port 5432, wie auf einem Rechner,
REM auf dem schon eine andere Anwendung ihre Datenbank betreibt. Gebaut mit
REM den gebuendelten Binaries - die gibt es erst nach setup.bat (EDB-
REM Installer), deshalb hier und nicht davor. setup.bat laeuft damit noch
REM ohne belegten Port; der Fremdserver trifft erst den Dienststart.
REM ============================================================
>> "%RES%" echo [Fremd-PG] Wegwerf-Cluster C:\foreignpg auf Port 5432 anlegen und starten ...
set "PGBIN=C:\PraxisZeit\bin\postgresql\bin"
"%PGBIN%\initdb.exe" -D C:\foreignpg -U postgres -A trust -E UTF8 > C:\pz-harness\foreign-initdb.log 2>&1
>> "%RES%" echo FOREIGN_INITDB_EXIT=!errorlevel!
"%PGBIN%\pg_ctl.exe" -D C:\foreignpg -l C:\pz-harness\foreignpg.log -o "-p 5432" -w start > C:\pz-harness\foreign-start.log 2>&1
>> "%RES%" echo FOREIGN_START_EXIT=!errorlevel!
type C:\pz-harness\foreign-start.log >> "%RES%" 2>&1
"%PGBIN%\pg_isready.exe" -h localhost -p 5432 >> "%RES%" 2>&1
>> "%RES%" echo FOREIGN_PG_READY_5432=!errorlevel!
:after_foreign_setup

>> "%RES%" echo [4/11] install-service.bat (NSSM) ...
call install-service.bat >> "%RES%" 2>&1

>> "%RES%" echo [5/11] net start PraxisZeit ...
net start PraxisZeit >> "%RES%" 2>&1

if /i not "!MODE!"=="foreignpg" goto :after_foreign_check
REM Negativprobe: mit dem Standard-Port 5432 muss der Dienst den fremden
REM Server erkennen, die Meldung nach logs\service-stderr.log schreiben und
REM mit Exit 78 stehen bleiben (NSSM AppExit 78 Exit - kein Neustart-Zyklus).
>> "%RES%" echo [Fremd-PG] Dienst mit Standard-Port: Exit 78 erwartet ...
for /l %%i in (1,1,36) do (
    timeout /t 5 /nobreak >nul
    sc query PraxisZeit | findstr /C:"STOPPED" >nul && goto :foreign_stopped
)
:foreign_stopped
sc query PraxisZeit | findstr /C:"STATE" /C:"EXIT_CODE" >> "%RES%" 2>&1
findstr /C:"ist von einem anderen PostgreSQL belegt" "C:\PraxisZeit\logs\service-stderr.log" >> "%RES%" 2>&1
if errorlevel 1 ( >> "%RES%" echo FOREIGN_DETECTED=0 ) else ( >> "%RES%" echo FOREIGN_DETECTED=1 )
REM Bleibt er wirklich stehen? 30 s spaeter darf NSSM ihn nicht neu gestartet haben.
timeout /t 30 /nobreak >nul
sc query PraxisZeit | findstr /C:"STOPPED" >nul && (>> "%RES%" echo FOREIGN_SERVICE_STAYS_STOPPED=1) || (>> "%RES%" echo FOREIGN_SERVICE_STAYS_STOPPED=0)
"%PGBIN%\pg_isready.exe" -h localhost -p 5432 >nul 2>&1
>> "%RES%" echo FOREIGN_PG_READY_NACH_NEGATIVPROBE=!errorlevel!
REM Was hat der abgebrochene Erststart hinterlassen? Ein angelegter Cluster
REM (Marker) ohne config\.db-credentials kann der naechste Start nicht mehr
REM uebernehmen.
if exist "C:\PraxisZeit\data\db\.praxiszeit-cluster" ( >> "%RES%" echo CLUSTER_MARKER_NACH_NEGATIVPROBE=1 ) else ( >> "%RES%" echo CLUSTER_MARKER_NACH_NEGATIVPROBE=0 )
if exist "C:\PraxisZeit\config\.db-credentials" ( >> "%RES%" echo CREDENTIALS_NACH_NEGATIVPROBE=1 ) else ( >> "%RES%" echo CREDENTIALS_NACH_NEGATIVPROBE=0 )
call :dump_logs NEGATIVPROBE
>> "%RES%" echo [Fremd-PG] [database] port = 5433 eintragen und Dienst erneut starten ...
powershell -NoProfile -Command "$p='C:\PraxisZeit\config\praxiszeit.conf'; $o=foreach($l in (Get-Content $p)){ $l; if($l -match '^\[database\]\s*$'){ 'port = 5433' } }; Set-Content $p $o -Encoding utf8" >> "%RES%" 2>&1
findstr /B /C:"port = " "C:\PraxisZeit\config\praxiszeit.conf" >> "%RES%" 2>&1
net start PraxisZeit >> "%RES%" 2>&1
:after_foreign_check

>> "%RES%" echo [6/11] Verifiziere HTTP (bis zu 6 min auf die App warten) ...
set "HC=000"
for /l %%i in (1,1,36) do (
    timeout /t 10 /nobreak >nul
    for /f %%c in ('curl -k -s -o nul -w "%%{http_code}" https://localhost/api/health') do set "HC=%%c"
    if "!HC!"=="200" goto :verified
)
:verified
>> "%RES%" echo HEALTH_HTTP=!HC!
if not "!HC!"=="200" call :dump_logs HEALTH
curl -k -s https://localhost/api/health >> "%RES%" 2>&1
>> "%RES%" echo.
for /f %%c in ('curl -k -s -o nul -w "%%{http_code}" -X POST https://localhost/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"!PWKEY!\":\"!ADMPW!\"}"') do >> "%RES%" echo LOGIN_HTTP=%%c

>> "%RES%" echo [7/11] Version pruefen (/api/system/info + openapi.json) ...
curl -k -s https://localhost/api/system/info > "%TEMP%\sysinfo.json" 2>nul
>> "%RES%" echo SYSTEM_INFO_RAW:
type "%TEMP%\sysinfo.json" >> "%RES%" 2>&1
>> "%RES%" echo.

>> "%RES%" echo [8/11] DB pruefen (alembic_version + PostgreSQL-Version) ...
REM Die Zugangsdaten legt der Installer selbst in config\.db-credentials ab.
REM psql bekommt sie ueber eine temporaere pgpass-Datei statt ueber eine
REM Umgebungsvariable - so steht in diesem Skript an keiner Stelle eine
REM Zuweisung, die wie ein hinterlegtes Kennwort aussieht. Die Datei wird
REM unmittelbar danach geloescht.
REM Der Port kommt aus der Installation selbst (print-db-port). Die
REM Vorgaengerversion im update-Lauf kennt den Befehl nicht - dann 5432.
call :read_db_port
set "PGPASSFILE=%TEMP%\pz-pgpass.conf"
del /f /q "%PGPASSFILE%" 2>nul
for /f "usebackq tokens=1,* delims==" %%a in (`findstr /B "SUPERUSER_PASSWORD=" "C:\PraxisZeit\config\.db-credentials"`) do >> "%PGPASSFILE%" echo 127.0.0.1:%DB_PORT%:praxiszeit:praxiszeit:%%b
if not exist "%PGPASSFILE%" ( >> "%RES%" echo ALEMBIC_VERSION=NO_DB_CREDENTIALS ) else (
    "C:\PraxisZeit\bin\postgresql\bin\psql.exe" -w -h 127.0.0.1 -p %DB_PORT% -U praxiszeit -d praxiszeit -tAc "SELECT version_num FROM alembic_version" > "%TEMP%\alembic.txt" 2>&1
    for /f "usebackq delims=" %%v in ("%TEMP%\alembic.txt") do >> "%RES%" echo ALEMBIC_VERSION=%%v
)
del /f /q "%PGPASSFILE%" 2>nul
set "PGPASSFILE="
sc query PraxisZeit | findstr STATE >> "%RES%" 2>&1
"C:\PraxisZeit\bin\postgresql\bin\psql.exe" --version >> "%RES%" 2>&1
call :own_check OWN_DETECTED
call :pgconf_md5 PGCONF_MD5

if /i not "!MODE!"=="update" goto :after_update
REM ============================================================
REM Update-Pfad: Ausgangsstand = Vorgaengerversion ohne Ordnerhaertung.
REM Erwartet VOR dem Update: INSTALLDIR_ACL_ALT meldet FAIL (der Mangel, den
REM das Update behebt). NACH dem Update: alles OK.
REM ============================================================
>> "%RES%" echo.
>> "%RES%" echo [Update] Ordnerrechte der Vorgaengerversion (FAIL erwartet) ...
>> "%RES%" echo ===INSTALLDIR_ACL_ALT_BEGIN===
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\pz-harness\install-acl-check.ps1" -InstallDir "C:\PraxisZeit" >> "%RES%" 2>&1
>> "%RES%" echo ===INSTALLDIR_ACL_ALT_END===
>> "%RES%" echo [Update] update-wizard.ps1 -Headless aus dem neuen Paket ...
robocopy "\\host.lan\Data\tree" "C:\PZNew" /E /R:2 /W:2 /NFL /NDL /NJH /NJS >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\PZNew\update-wizard.ps1" -InstallDir "C:\PraxisZeit" -Headless >> "%RES%" 2>&1
>> "%RES%" echo UPDATE_EXIT=!errorlevel!
findstr /C:"harden-permissions" "C:\PraxisZeit\praxiszeit-server.py" >nul && (>> "%RES%" echo NEUER_CODE=ja) || (>> "%RES%" echo NEUER_CODE=nein)
findstr /C:"print-db-port" "C:\PraxisZeit\praxiszeit-server.py" >nul && (>> "%RES%" echo NEUER_PORT_CODE=ja) || (>> "%RES%" echo NEUER_PORT_CODE=nein)
set "HCU=000"
for /l %%i in (1,1,36) do (
    for /f %%c in ('curl -k -s -o nul -w "%%{http_code}" https://localhost/api/health') do set "HCU=%%c"
    if "!HCU!"=="200" goto :verified_update
    timeout /t 10 /nobreak >nul
)
:verified_update
>> "%RES%" echo HEALTH_HTTP_NACH_UPDATE=!HCU!
for /f %%c in ('curl -k -s -o nul -w "%%{http_code}" -X POST https://localhost/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"!PWKEY!\":\"!ADMPW!\"}"') do >> "%RES%" echo LOGIN_HTTP_NACH_UPDATE=%%c
sc query PraxisZeit | findstr STATE >> "%RES%" 2>&1
call :read_db_port
call :own_check OWN_DETECTED_NACH_UPDATE
REM Ohne [database] port darf der neue Code postgresql.conf nicht anfassen.
call :pgconf_md5 PGCONF_MD5_NACH_UPDATE
if "!PGCONF_MD5!"=="!PGCONF_MD5_NACH_UPDATE!" ( >> "%RES%" echo PGCONF_UNVERAENDERT=ja ) else ( >> "%RES%" echo PGCONF_UNVERAENDERT=nein )
:after_update

REM ============================================================
REM Ordnerrechte des ganzen Installationsordners + echte Probe als
REM Standardkonto. Vorher eine Sicherung anlegen, damit data\backups
REM etwas enthaelt, das gelesen werden koennte.
REM ============================================================
>> "%RES%" echo.
>> "%RES%" echo [Ordner] Sicherung anlegen ...
set PYTHONUTF8=1
"C:\PraxisZeit\bin\python\python.exe" "C:\PraxisZeit\praxiszeit-server.py" backup >> "%RES%" 2>&1
>> "%RES%" echo BACKUP_EXIT=!errorlevel!
if /i not "!MODE!"=="foreignpg" goto :after_restore
REM ============================================================
REM foreignpg: restore-backup.bat muss den konfigurierten Port nehmen. Auf
REM 5432 saesse der Fremdserver (ohne Rolle praxiszeit) - jeder psql-Schritt
REM dort scheiterte. Bestaetigung "LOESCHEN" kommt aus einer Datei; pause
REM liest dort nur noch das Dateiende und haelt nicht an.
REM ============================================================
>> "%RES%" echo [Fremd-PG] restore-backup.bat mit der neuesten Sicherung ...
set "LATEST_BACKUP="
for /f "delims=" %%b in ('dir /b /o-d "C:\PraxisZeit\data\backups\*.sql.gz" 2^>nul') do if not defined LATEST_BACKUP set "LATEST_BACKUP=C:\PraxisZeit\data\backups\%%b"
>> "%RES%" echo RESTORE_BACKUP_FILE=!LATEST_BACKUP!
> "%TEMP%\pz-confirm.txt" echo LOESCHEN
set "PRAXISZEIT_INSTALL_DIR=C:\PraxisZeit"
call "C:\PraxisZeit\restore-backup.bat" "!LATEST_BACKUP!" < "%TEMP%\pz-confirm.txt" >> "%RES%" 2>&1
>> "%RES%" echo RESTORE_EXIT=!errorlevel!
del /f /q "%TEMP%\pz-confirm.txt" 2>nul
set "HCR=000"
for /l %%i in (1,1,36) do (
    for /f %%c in ('curl -k -s -o nul -w "%%{http_code}" https://localhost/api/health') do set "HCR=%%c"
    if "!HCR!"=="200" goto :verified_restore
    timeout /t 10 /nobreak >nul
)
:verified_restore
>> "%RES%" echo HEALTH_HTTP_NACH_RESTORE=!HCR!
for /f %%c in ('curl -k -s -o nul -w "%%{http_code}" -X POST https://localhost/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"!PWKEY!\":\"!ADMPW!\"}"') do >> "%RES%" echo LOGIN_HTTP_NACH_RESTORE=%%c
call :own_check OWN_DETECTED_NACH_RESTORE
REM 0 = der Fremdserver nimmt auf 5432 weiter Verbindungen an (pg_isready).
"C:\PraxisZeit\bin\postgresql\bin\pg_isready.exe" -h localhost -p 5432 >nul 2>&1
>> "%RES%" echo FOREIGN_PG_STILL_ON_5432=!errorlevel!
:after_restore
>> "%RES%" echo ===INSTALLDIR_ACL_BEGIN===
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\pz-harness\install-acl-check.ps1" -InstallDir "C:\PraxisZeit" >> "%RES%" 2>&1
>> "%RES%" echo ===INSTALLDIR_ACL_END===
>> "%RES%" echo ===PROBE_BEGIN===
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\pz-harness\run-probe.ps1" -InstallDir "C:\PraxisZeit" >> "%RES%" 2>&1
>> "%RES%" echo ===PROBE_END===

REM ============================================================
REM ACL-Nachweis: die beiden vertraulichen Dateien duerfen KEINE
REM Berechtigung fuer Users / Authenticated Users / Everyone tragen.
REM praxiszeit.conf = Admin-Passwort + Signaturschluessel
REM config\ssl\key.pem = privater TLS-Schluessel (vom Dienst erzeugt)
REM ============================================================
>> "%RES%" echo.
>> "%RES%" echo [9/11] ACL-Nachweis auf den Bestandsdateien ...
>> "%RES%" echo ===ACL_BESTAND_BEGIN===
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\acl-check.ps1" "C:\PraxisZeit\config\praxiszeit.conf" "C:\PraxisZeit\config\ssl\key.pem" "C:\PraxisZeit\config\ssl" >> "%RES%" 2>&1
>> "%RES%" echo ===ACL_BESTAND_END===

REM ============================================================
REM Frisch-Anlage-Pfad: die conf oben wurde vom Harness geschrieben
REM (simuliert den GUI-Installer) und von setup.bat nachgehaertet.
REM Hier wird zusaetzlich der ECHTE Neuanlage-Zweig aus setup.bat
REM geprueft: conf beiseite legen, setup.bat erneut laufen lassen
REM (PostgreSQL wird erkannt und uebersprungen), ACL messen,
REM Original zurueckkopieren.
REM ============================================================
>> "%RES%" echo.
>> "%RES%" echo [10/11] ACL-Nachweis auf dem Neuanlage-Zweig von setup.bat ...
REM foreignpg: der Dienst liest die conf alle 5 s neu. Ohne conf gilt Port 5432,
REM dort sitzt der Fremdserver - der Waechter wuerde mit Exit 78 aussteigen.
REM Deshalb hier anhalten; die Gegenprobe unten startet ihn wieder.
if /i "!MODE!"=="foreignpg" net stop PraxisZeit >> "%RES%" 2>&1
copy /Y "C:\PraxisZeit\config\praxiszeit.conf" "%TEMP%\praxiszeit.conf.bak" >nul
del /f /q "C:\PraxisZeit\config\praxiszeit.conf"
cd /d C:\PraxisZeit
call setup.bat >> "%RES%" 2>&1
>> "%RES%" echo ===ACL_NEUANLAGE_BEGIN===
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\acl-check.ps1" "C:\PraxisZeit\config\praxiszeit.conf" >> "%RES%" 2>&1
>> "%RES%" echo ===ACL_NEUANLAGE_END===
copy /Y "%TEMP%\praxiszeit.conf.bak" "C:\PraxisZeit\config\praxiszeit.conf" >nul
del /f /q "%TEMP%\praxiszeit.conf.bak"

REM ============================================================
REM Gegenprobe / Bestandsinstallation: die Rechte werden absichtlich wieder
REM aufgeweicht (Vererbung an + expliziter Lesezugriff fuer "Benutzer") - so
REM sieht eine Installation aus, die von einer aelteren Version stammt.
REM Der naechste Dienststart muss das selbst reparieren
REM (praxiszeit-server.py: _ensure_restricted_permissions) UND weiterhin
REM sauber hochkommen - eine zu strenge ACL wuerde das Dienstkonto aussperren.
REM ============================================================
>> "%RES%" echo.
>> "%RES%" echo [Gegenprobe] Rechte aufweichen wie bei einer Altinstallation ...
icacls "C:\PraxisZeit\config\praxiszeit.conf" /inheritance:e >> "%RES%" 2>&1
icacls "C:\PraxisZeit\config\praxiszeit.conf" /grant "*S-1-5-32-545:(R)" >> "%RES%" 2>&1
icacls "C:\PraxisZeit\config\ssl\key.pem" /inheritance:e >> "%RES%" 2>&1
icacls "C:\PraxisZeit\config\ssl\key.pem" /grant "*S-1-5-32-545:(R)" >> "%RES%" 2>&1
REM Ordner wie bei einer Altinstallation: Vererbung von C:\ wieder an
REM ("Authentifizierte Benutzer: Aendern") + data fuer Benutzer lesbar.
icacls "C:\PraxisZeit" /inheritance:e >> "%RES%" 2>&1
icacls "C:\PraxisZeit\data" /inheritance:e >> "%RES%" 2>&1
icacls "C:\PraxisZeit\data" /grant "*S-1-5-32-545:(OI)(CI)(R)" >> "%RES%" 2>&1
>> "%RES%" echo ===INSTALLDIR_ACL_AUFGEWEICHT_BEGIN===
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\pz-harness\install-acl-check.ps1" -InstallDir "C:\PraxisZeit" >> "%RES%" 2>&1
>> "%RES%" echo ===INSTALLDIR_ACL_AUFGEWEICHT_END===
>> "%RES%" echo ===ACL_AUFGEWEICHT_BEGIN===
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\acl-check.ps1" "C:\PraxisZeit\config\praxiszeit.conf" "C:\PraxisZeit\config\ssl\key.pem" >> "%RES%" 2>&1
>> "%RES%" echo ===ACL_AUFGEWEICHT_END===

>> "%RES%" echo [Gegenprobe] Dienst-Neustart - Selbstreparatur + Startfaehigkeit ...
net stop PraxisZeit >> "%RES%" 2>&1
net start PraxisZeit >> "%RES%" 2>&1
set "HC2=000"
for /l %%i in (1,1,36) do (
    timeout /t 10 /nobreak >nul
    for /f %%c in ('curl -k -s -o nul -w "%%{http_code}" https://localhost/api/health') do set "HC2=%%c"
    if "!HC2!"=="200" goto :verified2
)
:verified2
>> "%RES%" echo HEALTH_HTTP_NACH_NEUSTART=!HC2!
for /f %%c in ('curl -k -s -o nul -w "%%{http_code}" -X POST https://localhost/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"!PWKEY!\":\"!ADMPW!\"}"') do >> "%RES%" echo LOGIN_HTTP_NACH_NEUSTART=%%c
>> "%RES%" echo ===ACL_REPARIERT_BEGIN===
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\acl-check.ps1" "C:\PraxisZeit\config\praxiszeit.conf" "C:\PraxisZeit\config\ssl\key.pem" >> "%RES%" 2>&1
>> "%RES%" echo ===ACL_REPARIERT_END===
>> "%RES%" echo ===INSTALLDIR_ACL_REPARIERT_BEGIN===
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\pz-harness\install-acl-check.ps1" -InstallDir "C:\PraxisZeit" >> "%RES%" 2>&1
>> "%RES%" echo ===INSTALLDIR_ACL_REPARIERT_END===

REM ============================================================
REM GUI-Installer-Pfad (.NET): AclProbe ruft GENAU die Produktions-
REM methoden PraxisZeitConfigWriter.WriteAsync und
REM CertificateGenerator.Generate auf und legt die Dateien unter
REM C:\AclProbe an. Danach dieselbe ACL-Messung.
REM ============================================================
>> "%RES%" echo.
>> "%RES%" echo [11/11] ACL-Nachweis auf dem GUI-Installer-Pfad (.NET) ...
if exist "\\host.lan\Data\aclprobe\AclProbe.exe" (
    copy /Y "\\host.lan\Data\aclprobe\AclProbe.exe" "C:\AclProbe.exe" >nul
    "C:\AclProbe.exe" "C:\AclProbe" >> "%RES%" 2>&1
    >> "%RES%" echo ===ACL_DOTNET_BEGIN===
    powershell -NoProfile -ExecutionPolicy Bypass -File "C:\acl-check.ps1" "C:\AclProbe\config\praxiszeit.conf" "C:\AclProbe\config\ssl\key.pem" "C:\AclProbe\config\ssl\cert.pem" "C:\AclProbe\config\legacy-praxiszeit.conf" >> "%RES%" 2>&1
    >> "%RES%" echo ===ACL_DOTNET_END===
) else (
    >> "%RES%" echo AclProbe.exe nicht gefunden - Schritt uebersprungen.
)

REM ============================================================
REM Echter Neustart der VM: post-reboot.bat laeuft als geplante Aufgabe bei
REM der naechsten Anmeldung (dockur meldet automatisch an), prueft Dienst,
REM Anmeldung und Rechte erneut und schreibt erst dann "===== DONE =====".
REM ============================================================
>> "%RES%" echo.
>> "%RES%" echo [Neustart] geplante Aufgabe anlegen und VM neu starten ...
schtasks /create /tn PZPostReboot /sc onlogon /ru "%USERDOMAIN%\%USERNAME%" /it /rl highest /tr "C:\pz-harness\post-reboot.bat" /f >> "%RES%" 2>&1
if errorlevel 1 (
    >> "%RES%" echo REBOOT=UEBERSPRUNGEN ^(geplante Aufgabe nicht angelegt^)
    goto :done
)
call :stderr_probe
>> "%RES%" echo REBOOT=JETZT %date% %time%
shutdown /r /t 15 /c "PraxisZeit-Test: Neustart"
endlocal
exit /b 0

:done
>> "%RES%" echo.
>> "%RES%" echo Ende: %date% %time%
>> "%RES%" echo ===== DONE =====
endlocal
exit /b 0

REM ============================================================
REM Unterprogramme
REM ============================================================

:read_db_port
REM DB_PORT aus der Installation (praxiszeit-server.py print-db-port), sonst 5432.
REM Bewusst OHNE "2^>nul" in der Klammer: auf echtem cmd.exe kommt das als
REM Argument "2>nul" beim Programm an (siehe :stderr_probe), print-db-port
REM scheitert dann an argparse und DB_PORT bliebe leer.
set "DB_PORT="
for /f "usebackq delims=" %%p in (`""C:\PraxisZeit\bin\python\python.exe" "C:\PraxisZeit\praxiszeit-server.py" print-db-port"`) do set "DB_PORT=%%p"
if not defined DB_PORT (
    set "DB_PORT=5432"
    >> "%RES%" echo DB_PORT=5432 ^(Rueckfall: print-db-port nicht verfuegbar^)
) else (
    >> "%RES%" echo DB_PORT=!DB_PORT!
)
goto :eof

:dump_logs
REM %1 = Anlass. Letzte Zeilen der Dienst-Logs ins Ergebnis - ohne sie ist ein
REM gescheiterter Start von aussen nicht zu erklaeren.
>> "%RES%" echo ===LOGS_%~1_BEGIN===
>> "%RES%" echo --- logs\service-stderr.log
powershell -NoProfile -Command "Get-Content 'C:\PraxisZeit\logs\service-stderr.log' -Tail 40 -ErrorAction SilentlyContinue" >> "%RES%" 2>&1
>> "%RES%" echo --- logs\praxiszeit.log
powershell -NoProfile -Command "Get-Content 'C:\PraxisZeit\logs\praxiszeit.log' -Tail 40 -ErrorAction SilentlyContinue" >> "%RES%" 2>&1
>> "%RES%" echo ===LOGS_%~1_END===
goto :eof

:own_check
REM %1 = Ergebnisschluessel. praxiszeit-server.py status meldet "PostgreSQL:
REM running" nur, wenn der Cluster auf dem Port als UNSER Cluster erkannt wird
REM (pg_ctl status -D data\db + Port aus postmaster.pid) - aus der erhoehten
REM Harness-Shell, unter den gehaerteten Ordnerrechten.
"C:\PraxisZeit\bin\python\python.exe" "C:\PraxisZeit\praxiszeit-server.py" status > "%TEMP%\pz-status.txt" 2>&1
type "%TEMP%\pz-status.txt" >> "%RES%" 2>&1
findstr /C:"PostgreSQL: running" "%TEMP%\pz-status.txt" >nul
if errorlevel 1 ( >> "%RES%" echo %~1=0 ) else ( >> "%RES%" echo %~1=1 )
del /f /q "%TEMP%\pz-status.txt" 2>nul
goto :eof

:pgconf_md5
REM %1 = Schluessel; setzt die gleichnamige Variable und schreibt die port-Zeilen mit.
set "%~1="
for /f "usebackq delims=" %%h in (`powershell -NoProfile -Command "(Get-FileHash 'C:\PraxisZeit\data\db\postgresql.conf' -Algorithm MD5).Hash"`) do set "%~1=%%h"
>> "%RES%" echo %~1=!%~1!
findstr /R /C:"^port" /C:"^#port" "C:\PraxisZeit\data\db\postgresql.conf" >> "%RES%" 2>&1
goto :eof

:stderr_probe
REM Unterdrueckt "2^>nul" in der gequoteten for-/f-Zeile (setup.bat,
REM uninstall.bat) auf echtem cmd.exe die Fehlerausgabe? Gleiche Form; ein
REM Python-Einzeiler schreibt STDERR_LEAK nach stderr und seine Argumente
REM (STDERR_PROBE_*_ARGS=[...]) nach stdout. Gegenprobe ohne "2^>nul": dort
REM MUSS STDERR_LEAK ankommen, sonst beweist die erste Zeile nichts.
> "C:\pz-harness\stderr-probe.py" echo import sys; sys.stderr.write("STDERR_LEAK\n"); print("ARGS=" + repr(sys.argv[1:]))
set "PROBE_PY=C:\PraxisZeit\bin\python\python.exe"
set "SP="
(for /f "usebackq delims=" %%p in (`""%PROBE_PY%" "C:\pz-harness\stderr-probe.py" 2^>nul"`) do set "SP=%%p") > "%TEMP%\pz-sp-mit.txt" 2>&1
findstr /C:"STDERR_LEAK" "%TEMP%\pz-sp-mit.txt" >nul
if errorlevel 1 ( >> "%RES%" echo STDERR_LEAK_MIT_2NUL=0 ) else ( >> "%RES%" echo STDERR_LEAK_MIT_2NUL=1 )
>> "%RES%" echo STDERR_PROBE_MIT_2NUL_!SP!
set "SP="
(for /f "usebackq delims=" %%p in (`""%PROBE_PY%" "C:\pz-harness\stderr-probe.py""`) do set "SP=%%p") > "%TEMP%\pz-sp-ohne.txt" 2>&1
findstr /C:"STDERR_LEAK" "%TEMP%\pz-sp-ohne.txt" >nul
if errorlevel 1 ( >> "%RES%" echo STDERR_LEAK_OHNE_2NUL=0 ) else ( >> "%RES%" echo STDERR_LEAK_OHNE_2NUL=1 )
>> "%RES%" echo STDERR_PROBE_OHNE_2NUL_!SP!
del /f /q "%TEMP%\pz-sp-mit.txt" "%TEMP%\pz-sp-ohne.txt" 2>nul
goto :eof
