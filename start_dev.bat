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

echo [2/3] Starting both Backend and Frontend in THIS window...
echo Please wait... (Press Ctrl+C to stop both servers)
echo.

npx -y concurrently -k -p "[{name}]" -n "BACK,FRONT" -c "bgBlue.bold,bgMagenta.bold" "cd backend && python run.py local" "cd frontend && npm run dev"
