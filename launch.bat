@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
title LinkedIn Job Automation Dashboard
cd /d "%~dp0"

echo ===================================================
echo   Starting EasiApply Job Automation Dashboard...
echo ===================================================
echo.
echo [INFO] Working directory: %CD%
echo.

:: Keep a crash log so flash-closes still leave a trail
mkdir "%CD%\logs" 2>nul
set "LOG=%CD%\logs\launch_error.log"
echo Launch started at %DATE% %TIME% > "%LOG%"

:: Prefer `py -3` if available, else python
set "PY=python"
where py >nul 2>&1 && set "PY=py -3"

%PY% --version >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not found in your PATH.
    echo Please install Python 3 and tick "Add python.exe to PATH".
    echo.
    echo Full details were written to: %LOG%
    goto :hold
)

echo [INFO] Using: %PY%
%PY% --version
echo.

:: Kill orphaned listeners on port 8000 (ignore failures)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000" ^| find "LISTENING"') do (
    echo [INFO] Found orphaned process on port 8000, terminating PID %%a...
    taskkill /F /PID %%a >nul 2>&1
)

:: Preflight: initialize .env if missing
if not exist "%CD%\.env" (
    if exist "%CD%\.env.example" (
        echo [INFO] Initializing .env from .env.example...
        copy "%CD%\.env.example" "%CD%\.env" >nul
    )
)

:: Preflight: can we import the FastAPI app?
echo [INFO] Checking dependencies and app import...
%PY% -c "import fastapi, uvicorn; from src.api.server import app; print('OK: app imported')" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] App failed to import. Installing requirements, then retrying...
    echo.
    %PY% -m pip install -r requirements.txt >> "%LOG%" 2>&1
    %PY% -c "import fastapi, uvicorn; from src.api.server import app; print('OK: app imported')" >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo [ERROR] Still cannot import the server.
        echo.
        type "%LOG%"
        echo.
        echo ---- end of %LOG% ----
        goto :hold
    )
)

:: Preflight: ensure Playwright Chromium browser binary is installed
echo [INFO] Checking Playwright browser binaries...
%PY% -c "import sys; from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); b.close(); p.stop(); sys.exit(0)" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [INFO] Playwright Chromium not found. Installing browser binaries - one-time setup...
    %PY% -m playwright install chromium
)

echo [INFO] Launching EasiApply Dashboard...
echo [INFO] Server starting on http://127.0.0.1:8000
echo [INFO] Browser will open automatically
echo [INFO] Leave this window open while using the dashboard
echo.

:: Open browser after a short delay (separate process)
start "" %PY% -c "import time, webbrowser; time.sleep(2); webbrowser.open('http://127.0.0.1:8000/dashboard')"

:: Run server in the foreground so you see live errors
%PY% -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
set "ERR=%ERRORLEVEL%"

echo.
if not "%ERR%"=="0" (
    echo [ERROR] Server exited with code %ERR%
    echo [ERROR] Last log lines:
    type "%LOG%"
    echo Server exit code %ERR% at %DATE% %TIME% >> "%LOG%"
)

:hold
echo.
echo Press any key to close this window...
pause >nul
endlocal
exit /b %ERR%
