@echo off
setlocal
title Intonation Debug Lab - Launcher
cd /d "%~dp0"

echo ==============================================
echo   Intonation Debug Lab  -  Pitch Curve Editor
echo ==============================================
echo.

rem ============ 1. locate a usable Python ============
set "PY="
set "PY_ARGS="
if exist ".venv\Scripts\python.exe" call :try_python "%CD%\.venv\Scripts\python.exe"
if defined PY goto :python_ok
for /f "delims=" %%p in ('where python 2^>nul') do if not defined PY call :try_python "%%p"
if defined PY goto :python_ok
for /f "delims=" %%p in ('where py 2^>nul') do if not defined PY call :try_py "%%p"
if defined PY goto :python_ok
echo [ERROR] Python not found.
echo Please install or repair Python 3.10 or newer and make python.exe or py.exe available.
echo A stale virtual environment is ignored automatically.
pause
exit /b 1

:python_ok
echo [1/4] Python: %PY% %PY_ARGS%

rem ============ 2. dependencies ============
"%PY%" %PY_ARGS% -c "import streamlit, numpy, soundfile" >nul 2>nul
if not errorlevel 1 goto :deps_ok
echo [2/4] Installing dependencies on first run, please wait...
"%PY%" %PY_ARGS% -m pip install -r requirements.txt
if not errorlevel 1 goto :deps_ok
echo [ERROR] Dependency install failed. Please check your network.
pause
exit /b 1

:deps_ok
echo [2/4] Dependencies OK

rem ============ 3. verify port 8507 ============
echo [3/4] Checking port 8507...
set "PORT_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8507" ^| findstr "LISTENING"') do if not defined PORT_PID set "PORT_PID=%%a"
if defined PORT_PID (
    echo [ERROR] Port 8507 is already used by PID %PORT_PID%.
    echo Close that program or server first; it will not be terminated automatically.
    pause
    exit /b 1
)

rem ============ 4. start server and open browser ============
echo [4/4] Starting server: http://localhost:8507
if "%DSH_NO_BROWSER%"=="1" goto :no_browser
start "" /b cmd /c "ping -n 5 127.0.0.1 >nul & start http://localhost:8507"

:no_browser
"%PY%" %PY_ARGS% -m streamlit run app.py --server.headless=true --server.address=localhost --server.port=8507 --browser.gatherUsageStats=false

echo.
echo Server stopped. Press any key to close this window.
pause
exit /b 0

:try_python
if defined PY exit /b 0
"%~1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 (
    set "PY=%~1"
    set "PY_ARGS="
)
exit /b 0

:try_py
if defined PY exit /b 0
"%~1" -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 (
    set "PY=%~1"
    set "PY_ARGS=-3"
)
exit /b 0
