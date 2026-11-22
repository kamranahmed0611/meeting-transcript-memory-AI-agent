@echo off
title Catalist Meeting Memory Engine - Web Application
cd /d "%~dp0"
cls
echo ======================================================================
echo           CATALIST MEDIA: MEETING INTELLIGENCE ENGINE
echo ======================================================================
echo.
echo [1/3] Checking Python virtual environment (.venv)...

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [2/3] Starting Local Web Server on http://localhost:8080...
echo [3/3] Opening browser...
echo.

start "" "http://localhost:8080"
"%PYTHON_EXE%" app.py 8080

pause
