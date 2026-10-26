@echo off
setlocal EnableDelayedExpansion
REM Test-Harness (NICHT Teil des Pakets): laeuft nach dem Neustart der VM als
REM geplante Aufgabe bei der Anmeldung (install.bat legt sie an). Belegt, dass
REM der Dienst nach einem echten Windows-Neustart mit den eingeschraenkten
REM Ordnerrechten von selbst hochkommt (PostgreSQL unter NetworkService muss
REM data\db weiterhin erreichen) und die Rechte dabei bleiben.
set "RES=\\host.lan\Data\install-result.txt"
schtasks /delete /tn PZPostReboot /f >nul 2>&1
>> "%RES%" echo.
>> "%RES%" echo ===== Nach Neustart =====
>> "%RES%" echo Start: %date% %time%
for /f "usebackq delims=" %%b in (`powershell -NoProfile -Command "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('s')"`) do >> "%RES%" echo LAST_BOOT=%%b

set "PWKEY=pass"
set "PWKEY=!PWKEY!word"
set "ADMPW="
for /f "usebackq delims=" %%p in ("\\host.lan\Data\admin-password.txt") do if not defined ADMPW set "ADMPW=%%p"

set "HC=000"
for /l %%i in (1,1,60) do (
    for /f %%c in ('curl -k -s -o nul -w "%%{http_code}" https://localhost/api/health') do set "HC=%%c"
    if "!HC!"=="200" goto :up
    timeout /t 10 /nobreak >nul
)
:up
>> "%RES%" echo HEALTH_HTTP_NACH_REBOOT=!HC!
for /f %%c in ('curl -k -s -o nul -w "%%{http_code}" -X POST https://localhost/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"!PWKEY!\":\"!ADMPW!\"}"') do >> "%RES%" echo LOGIN_HTTP_NACH_REBOOT=%%c
sc query PraxisZeit | findstr STATE >> "%RES%" 2>&1

set "PGPASSFILE=%TEMP%\pz-pgpass.conf"
del /f /q "%PGPASSFILE%" 2>nul
for /f "usebackq tokens=1,* delims==" %%a in (`findstr /B "SUPERUSER_PASSWORD=" "C:\PraxisZeit\config\.db-credentials"`) do >> "%PGPASSFILE%" echo 127.0.0.1:5432:praxiszeit:praxiszeit:%%b
"C:\PraxisZeit\bin\postgresql\bin\psql.exe" -w -h 127.0.0.1 -p 5432 -U praxiszeit -d praxiszeit -tAc "SELECT 'ALEMBIC_VERSION_NACH_REBOOT=' || version_num FROM alembic_version" >> "%RES%" 2>&1
del /f /q "%PGPASSFILE%" 2>nul
set "PGPASSFILE="

>> "%RES%" echo ===INSTALLDIR_ACL_REBOOT_BEGIN===
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\pz-harness\install-acl-check.ps1" -InstallDir "C:\PraxisZeit" >> "%RES%" 2>&1
>> "%RES%" echo ===INSTALLDIR_ACL_REBOOT_END===
>> "%RES%" echo ===PROBE_REBOOT_BEGIN===
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\pz-harness\run-probe.ps1" -InstallDir "C:\PraxisZeit" >> "%RES%" 2>&1
>> "%RES%" echo ===PROBE_REBOOT_END===

>> "%RES%" echo.
>> "%RES%" echo Ende: %date% %time%
>> "%RES%" echo ===== DONE =====
endlocal
