@echo off
REM PraxisZeit Windows Service Uninstallation

SET NSSM=%~dp0nssm.exe

echo PraxisZeit Service Uninstaller
echo ==============================

REM Stop service
echo Stopping PraxisZeit service...
net stop PraxisZeit 2>nul

REM Remove service
echo Removing service...
"%NSSM%" remove PraxisZeit confirm

REM Remove firewall rule
echo Removing firewall rule...
netsh advfirewall firewall delete rule name="PraxisZeit"

echo.
echo Service removed.
echo.
echo NOTE: Database files in data\ have been preserved.
echo To completely remove all data, delete the installation directory.
echo.

pause
