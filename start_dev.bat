@echo off
echo ===================================================
echo StockAuto Local Development Startup Script
echo ===================================================
echo.

echo [1/3] Checking Redis (Memurai) status...
tasklist | find /I "memurai" >nul
if errorlevel 1 (
    echo [WARNING] Memurai process not found.
    echo Please start 'memurai' from Windows Services or run 'net start memurai' as Admin.
) else (
    echo [OK] Memurai is running.
)
echo.

echo [2/3] Starting Backend (FastAPI)...
start "StockAuto Backend" cmd /k "cd backend && python run.py local"
echo [OK] Backend terminal launched.
echo.

echo [3/3] Starting Frontend (Next.js)...
start "StockAuto Frontend" cmd /k "cd frontend && npm run dev"
echo [OK] Frontend terminal launched.
echo.

echo ===================================================
echo All servers launched! Check the new terminal windows.
echo This window will close in 5 seconds.
echo ===================================================
timeout /t 5 >nul
