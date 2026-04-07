@echo off
REM PraxisZeit Windows Service Installation
REM Requires nssm.exe in the same directory or in PATH

SET INSTALL_DIR=%~dp0..
SET NSSM=%~dp0nssm.exe
SET PYTHON=%INSTALL_DIR%\bin\python\python.exe
SET SCRIPT=%INSTALL_DIR%\praxiszeit-server.py

echo PraxisZeit Windows Service Installer
echo =====================================

REM Check if nssm exists
if not exist "%NSSM%" (
    echo ERROR: nssm.exe not found at %NSSM%
    echo Download from https://nssm.cc/download
    pause
    exit /b 1
)

REM Check if Python exists
if not exist "%PYTHON%" (
    echo ERROR: Python not found at %PYTHON%
    pause
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

echo.
echo Service installed successfully.
echo Start with: net start PraxisZeit
echo Stop with:  net stop PraxisZeit
echo.

REM Add firewall rule
echo Adding firewall rule...
netsh advfirewall firewall add rule name="PraxisZeit" dir=in action=allow protocol=TCP localport=443
echo Firewall rule added for port 443.

pause
