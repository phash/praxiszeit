@echo off
setlocal DisableDelayedExpansion
REM ============================================================
REM PraxisZeit Update-Wizard Launcher
REM Prueft Admin-Rechte und startet das PowerShell-GUI.
REM Aufruf: update-wizard.bat [InstallDir]
REM ============================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo FEHLER: Der Update-Wizard muss als Administrator ausgefuehrt werden.
    echo.
    echo Rechtsklick auf update-wizard.bat
    echo     -^> "Als Administrator ausfuehren"
    echo.
    pause
    exit /b 1
)

SET "DIR=%~dp0"
SET "WIZARD=%DIR%update-wizard.ps1"

if not exist "%WIZARD%" (
    echo FEHLER: %WIZARD% nicht gefunden.
    pause
    exit /b 1
)

REM UTF-8 fuer Umlaute in PowerShell-Strings
SET "PYTHONUTF8=1"
chcp 65001 >nul

powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%WIZARD%" %*
exit /b %errorlevel%
