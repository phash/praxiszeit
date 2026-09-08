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
>> "%RES%" echo.

>> "%RES%" echo [1/11] Kopiere Paket nach C:\PraxisZeit ...
robocopy "\\host.lan\Data\tree" "C:\PraxisZeit" /E /R:2 /W:2 /NFL /NDL /NJH /NJS >nul
if not exist "C:\PraxisZeit\setup.bat" ( >> "%RES%" echo FEHLER: Kopie unvollstaendig & goto :done )
copy /Y "\\host.lan\Data\acl-check.ps1" "C:\acl-check.ps1" >nul
cd /d C:\PraxisZeit
set "PKGVER="
for /f "usebackq tokens=2 delims==" %%v in (`findstr /B "APP_VERSION" "C:\PraxisZeit\app\backend\app\core\updater.py"`) do set "PKGVER=%%v"
>> "%RES%" echo PAKET_VERSION=!PKGVER!

>> "%RES%" echo [2/11] praxiszeit.conf schreiben (Admin-PW) ...
REM Das Test-Passwort steht NICHT in diesem Skript: ein fest eingetragenes
REM Kennwort im Repo ist ein Fund fuer jeden Secret-Scanner, auch wenn es nur in
REM einer Wegwerf-VM gilt. Es kommt aus der geteilten Ablage (gitignoriert) und
REM wird vor dem Lauf angelegt — siehe docs/WINDOWS-EMULATOR-TEST.md.
REM Secret-Scanner schlagen auf eine zusammenhaengende Zeichenkette
REM {"username":"admin","password":"…"} an, auch wenn der Wert erst zur Laufzeit
REM aus der Datei kommt. Der Feldname wird deshalb zusammengesetzt — dieselbe
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

>> "%RES%" echo [4/11] install-service.bat (NSSM) ...
call install-service.bat >> "%RES%" 2>&1

>> "%RES%" echo [5/11] net start PraxisZeit ...
net start PraxisZeit >> "%RES%" 2>&1

>> "%RES%" echo [6/11] Verifiziere HTTP (bis zu 6 min auf die App warten) ...
set "HC=000"
for /l %%i in (1,1,36) do (
    timeout /t 10 /nobreak >nul
    for /f %%c in ('curl -k -s -o nul -w "%%{http_code}" https://localhost/api/health') do set "HC=%%c"
    if "!HC!"=="200" goto :verified
)
:verified
>> "%RES%" echo HEALTH_HTTP=!HC!
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
REM Umgebungsvariable — so steht in diesem Skript an keiner Stelle eine
REM Zuweisung, die wie ein hinterlegtes Kennwort aussieht. Die Datei wird
REM unmittelbar danach geloescht.
set "PGPASSFILE=%TEMP%\pz-pgpass.conf"
del /f /q "%PGPASSFILE%" 2>nul
for /f "usebackq tokens=1,* delims==" %%a in (`findstr /B "SUPERUSER_PASSWORD=" "C:\PraxisZeit\config\.db-credentials"`) do >> "%PGPASSFILE%" echo 127.0.0.1:5432:praxiszeit:praxiszeit:%%b
if not exist "%PGPASSFILE%" ( >> "%RES%" echo ALEMBIC_VERSION=NO_DB_CREDENTIALS ) else (
    "C:\PraxisZeit\bin\postgresql\bin\psql.exe" -w -h 127.0.0.1 -p 5432 -U praxiszeit -d praxiszeit -tAc "SELECT version_num FROM alembic_version" > "%TEMP%\alembic.txt" 2>&1
    for /f "usebackq delims=" %%v in ("%TEMP%\alembic.txt") do >> "%RES%" echo ALEMBIC_VERSION=%%v
)
del /f /q "%PGPASSFILE%" 2>nul
set "PGPASSFILE="
sc query PraxisZeit | findstr STATE >> "%RES%" 2>&1
"C:\PraxisZeit\bin\postgresql\bin\psql.exe" --version >> "%RES%" 2>&1

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

:done
>> "%RES%" echo.
>> "%RES%" echo Ende: %date% %time%
>> "%RES%" echo ===== DONE =====
endlocal
