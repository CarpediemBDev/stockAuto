@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0"
set "BACKEND_DIR=%PROJECT_ROOT%backend"
set "FRONTEND_DIR=%PROJECT_ROOT%frontend"
set "BACKEND_PYTHON=%BACKEND_DIR%\venv\Scripts\python.exe"
set "CHECK_ONLY=0"
set "KILL_ONLY=0"

:parse_args
if "%~1"=="" goto :args_done
if /I "%~1"=="--check" (
    set "CHECK_ONLY=1"
    shift
    goto :parse_args
)
if /I "%~1"=="--kill" (
    shift
    goto :parse_args
)
if /I "%~1"=="--restart" (
    shift
    goto :parse_args
)
if /I "%~1"=="--stop" (
    set "KILL_ONLY=1"
    shift
    goto :parse_args
)
if /I "%~1"=="--kill-only" (
    set "KILL_ONLY=1"
    shift
    goto :parse_args
)
echo [FAIL] Unsupported argument: %1
echo Usage: start_dev.bat [--check] [--kill] [--restart] [--stop]
exit /b 2

:args_done


pushd "%PROJECT_ROOT%" >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Cannot open project root: %PROJECT_ROOT%
    exit /b 1
)

echo =============================================================
echo StockAuto local development preflight
echo =============================================================

if not exist "%BACKEND_PYTHON%" (
    set "ERROR_MESSAGE=Backend virtual environment is missing. Run: cd backend ^&^& python -m venv venv"
    goto :fail
)

"%BACKEND_PYTHON%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    set "ERROR_MESSAGE=Backend packages are missing. Run: backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt"
    goto :fail
)
echo [OK] Backend virtual environment and packages

if not exist "%BACKEND_DIR%\.env.local" (
    set "ERROR_MESSAGE=backend\.env.local is missing. Copy backend\.env.local.example and configure it."
    goto :fail
)

findstr /R /C:"^REDIS_URL=." "%BACKEND_DIR%\.env.local" >nul 2>&1
if errorlevel 1 (
    set "ERROR_MESSAGE=backend\.env.local requires a non-empty REDIS_URL value."
    goto :fail
)
echo [OK] Backend local environment file

where node.exe >nul 2>&1
if errorlevel 1 (
    set "ERROR_MESSAGE=Node.js was not found. Install Node.js 20.9.0 or newer."
    goto :fail
)

set "NODE_MAJOR="
set "NODE_MINOR="
for /F "tokens=1,2 delims=." %%A in ('node.exe -p "process.versions.node"') do (
    set "NODE_MAJOR=%%A"
    set "NODE_MINOR=%%B"
)
if not defined NODE_MAJOR (
    set "ERROR_MESSAGE=Unable to determine the Node.js version."
    goto :fail
)
if %NODE_MAJOR% LSS 20 (
    set "ERROR_MESSAGE=Node.js 20.9.0 or newer is required."
    goto :fail
)
if %NODE_MAJOR% EQU 20 if %NODE_MINOR% LSS 9 (
    set "ERROR_MESSAGE=Node.js 20.9.0 or newer is required."
    goto :fail
)

where npm.cmd >nul 2>&1
if errorlevel 1 (
    set "ERROR_MESSAGE=npm.cmd was not found. Repair the Node.js installation."
    goto :fail
)

if not exist "%FRONTEND_DIR%\node_modules\.bin\next.cmd" (
    set "ERROR_MESSAGE=Frontend packages are missing. Run: cd frontend ^&^& npm install"
    goto :fail
)

if not exist "%FRONTEND_DIR%\.env.local" (
    set "ERROR_MESSAGE=frontend\.env.local is missing. Copy frontend\.env.example and configure it."
    goto :fail
)
echo [OK] Node.js, npm, and frontend local environment

call :port_open 6379
if not errorlevel 1 goto :redis_ready

if "%CHECK_ONLY%"=="1" (
    set "ERROR_MESSAGE=Redis is not reachable at 127.0.0.1:6379."
    goto :fail
)

echo [INFO] Redis is not running. Trying to start Memurai...

REM Prefer the registered Memurai Windows service (requires elevation).
net start Memurai >nul 2>&1

call :port_open 6379
if not errorlevel 1 goto :redis_ready

REM Service unavailable or needs admin: launch the Memurai binary directly.
set "MEMURAI_EXE=%ProgramFiles%\Memurai\memurai.exe"
if not exist "%MEMURAI_EXE%" (
    for /f "delims=" %%I in ('where memurai.exe 2^>nul') do set "MEMURAI_EXE=%%I"
)
if not exist "%MEMURAI_EXE%" (
    set "ERROR_MESSAGE=Redis is stopped and Memurai was not found. Install Memurai (https://www.memurai.com) or start Redis on 127.0.0.1:6379."
    goto :fail
)

start "StockAuto Redis" /MIN "%MEMURAI_EXE%" --port 6379 --save "" --appendonly no

set /a REDIS_WAIT_COUNT=0
:wait_redis
call :port_open 6379
if not errorlevel 1 goto :redis_ready
set /a REDIS_WAIT_COUNT+=1
if %REDIS_WAIT_COUNT% GEQ 15 (
    set "ERROR_MESSAGE=Memurai did not open port 6379 within 15 seconds."
    goto :fail
)
powershell.exe -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 1" >nul 2>&1
goto :wait_redis

:redis_ready
echo [OK] Redis at 127.0.0.1:6379

if "%CHECK_ONLY%"=="1" (
    call :port_open 8000
    if not errorlevel 1 (
        call :url_contains "http://127.0.0.1:8000/" "StockAuto" 5
        if errorlevel 1 (
            set "ERROR_MESSAGE=Port 8000 is used by a service other than StockAuto. Stop that process and retry."
            goto :fail
        )
        echo [OK] StockAuto backend is already running on port 8000
    )

    call :port_open 3000
    if not errorlevel 1 (
        call :url_contains "http://127.0.0.1:3000/" "StockAuto" 15
        if errorlevel 1 (
            set "ERROR_MESSAGE=Port 3000 is used by a service other than StockAuto. Stop that process and retry."
            goto :fail
        )
        echo [OK] StockAuto frontend is already running on port 3000
    )

    echo [OK] Development port ownership
    echo =============================================================
    echo [PASS] All checks passed. No server was started.
    echo =============================================================
    popd
    exit /b 0
)

echo =============================================================
echo [INFO] Terminating existing StockAuto processes and freeing ports...
echo =============================================================

:: 1. Close cmd windows with titles starting with StockAuto Backend or StockAuto Frontend
taskkill /F /FI "WINDOWTITLE eq StockAuto Backend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq StockAuto Frontend*" >nul 2>&1

:: 2. Find and kill process tree listening on port 8000 (Backend)
for /f "tokens=5" %%A in ('netstat -ano ^| findstr /R /C:"[.:]8000 " ^| findstr LISTENING') do (
    if not "%%A"=="0" (
        echo Terminating backend process tree ^(PID %%A^) on port 8000...
        taskkill /F /T /PID %%A >nul 2>&1
    )
)

:: 3. Find and kill process tree listening on port 3000 (Frontend)
for /f "tokens=5" %%A in ('netstat -ano ^| findstr /R /C:"[.:]3000 " ^| findstr LISTENING') do (
    if not "%%A"=="0" (
        echo Terminating frontend process tree ^(PID %%A^) on port 3000...
        taskkill /F /T /PID %%A >nul 2>&1
    )
)

:: 4. Wait for OS socket release (up to 5 seconds)
set /a PORT_RELEASE_WAIT=0
:wait_ports_release
set "PORTS_RELEASED=1"
call :port_open 8000
if not errorlevel 1 set "PORTS_RELEASED=0"
call :port_open 3000
if not errorlevel 1 set "PORTS_RELEASED=0"
if "%PORTS_RELEASED%"=="1" goto :ports_clean
set /a PORT_RELEASE_WAIT+=1
if %PORT_RELEASE_WAIT% GEQ 5 goto :ports_clean
powershell.exe -NoProfile -NonInteractive -Command "Start-Sleep -Milliseconds 500" >nul 2>&1
goto :wait_ports_release

:ports_clean

if "%KILL_ONLY%"=="1" (
    echo =============================================================
    echo [PASS] Existing StockAuto processes terminated successfully.
    echo =============================================================
    popd
    exit /b 0
)

call :port_open 8000
if not errorlevel 1 (
    call :url_contains "http://127.0.0.1:8000/" "StockAuto" 5
    if errorlevel 1 (
        set "ERROR_MESSAGE=Port 8000 is occupied by another service. Stop that process and retry."
        goto :fail
    )
)
call :port_open 3000
if not errorlevel 1 (
    call :url_contains "http://127.0.0.1:3000/" "StockAuto" 15
    if errorlevel 1 (
        set "ERROR_MESSAGE=Port 3000 is occupied by another service. Stop that process and retry."
        goto :fail
    )
)
echo [OK] Development port ownership

echo.
echo [1/2] Starting backend: http://localhost:8000
start "StockAuto Backend" /D "%BACKEND_DIR%" cmd.exe /k "venv\Scripts\python.exe run.py local"

echo [2/2] Starting frontend: http://localhost:3000
start "StockAuto Frontend" /D "%FRONTEND_DIR%" cmd.exe /k "call npm.cmd run local"

echo [INFO] Waiting for both servers to become ready...
set /a SERVER_WAIT_COUNT=0
:wait_servers
call :port_open 8000
set "BACKEND_READY=%errorlevel%"
call :port_open 3000
set "FRONTEND_READY=%errorlevel%"
if "%BACKEND_READY%"=="0" if "%FRONTEND_READY%"=="0" goto :servers_ready
set /a SERVER_WAIT_COUNT+=1
if %SERVER_WAIT_COUNT% GEQ 30 (
    set "ERROR_MESSAGE=One or both servers did not become ready within 30 seconds. Review the opened terminal errors."
    goto :fail
)
powershell.exe -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 1" >nul 2>&1
goto :wait_servers

:servers_ready
echo =============================================================
echo [PASS] Backend and frontend are ready.
echo Press Ctrl+C in each terminal to stop the servers.
echo =============================================================
powershell.exe -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 5" >nul 2>&1
popd
exit /b 0

:fail
echo.
echo =============================================================
echo [FAIL] %ERROR_MESSAGE%
echo =============================================================
popd
exit /b 1

:port_open
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$client=[Net.Sockets.TcpClient]::new(); try {$task=$client.ConnectAsync('127.0.0.1',%~1); if (-not $task.Wait(1000)) {exit 1}; if ($client.Connected) {exit 0}; exit 1} catch {exit 1} finally {$client.Dispose()}" >nul 2>&1
exit /b %errorlevel%

:url_contains
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "try {$response=Invoke-WebRequest -UseBasicParsing -Uri '%~1' -TimeoutSec %~3; if ($response.Content -like '*%~2*') {exit 0}; exit 1} catch {exit 1}" >nul 2>&1
exit /b %errorlevel%
