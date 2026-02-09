@echo off
echo.
echo ========================================
echo   PraxisZeit - Zeiterfassungssystem
echo ========================================
echo.

cd /d "%~dp0"

echo [1/3] Starte Docker Container...
docker-compose up -d

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo FEHLER: Docker-Container konnten nicht gestartet werden.
    echo Stelle sicher, dass Docker Desktop lauft.
    pause
    exit /b 1
)

echo.
echo [2/3] Warte auf Services...
timeout /t 5 /nobreak >nul

echo.
echo [3/3] Prufe Status...
docker-compose ps

echo.
echo ========================================
echo   Server erfolgreich gestartet!
echo ========================================
echo.
echo   Frontend:  http://localhost
echo   API Docs:  http://localhost:8000/docs
echo.
echo   Login: admin@example.com / admin123
echo.
echo ========================================
echo.
echo Zum Stoppen: stop.bat ausfuhren
echo.

pause
