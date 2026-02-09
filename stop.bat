@echo off
echo.
echo ========================================
echo   PraxisZeit - Server stoppen
echo ========================================
echo.

cd /d "%~dp0"

echo Stoppe Docker Container...
docker-compose down

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo FEHLER: Fehler beim Stoppen der Container.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Server erfolgreich gestoppt!
echo ========================================
echo.
echo Alle Container wurden gestoppt.
echo Daten bleiben im Volume erhalten.
echo.

pause
