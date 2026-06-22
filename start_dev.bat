@echo off
chcp 65001 >nul
echo ===================================================
echo 🚀 StockAuto 로컬 개발 환경 시작 스크립트
echo ===================================================
echo.

echo [1/3] Redis(Memurai) 상태 확인 중...
tasklist | find /I "memurai" >nul
if errorlevel 1 (
    echo [경고] Memurai 프로세스가 발견되지 않았습니다.
    echo 관리자 권한으로 'net start memurai'를 실행하거나 작업 관리자의 [서비스] 탭에서 직접 켜주세요.
) else (
    echo [완료] Memurai(Redis)가 정상 실행 중입니다.
)
echo.

echo [2/3] 백엔드(FastAPI) 서버 구동 중...
start "StockAuto Backend" cmd /k "cd backend && call venv\Scripts\activate.bat && python run.py local"
echo [완료] 백엔드 터미널 창을 열었습니다. (가상 환경 및 local 모드)
echo.

echo [3/3] 프론트엔드(Next.js) 서버 구동 중...
start "StockAuto Frontend" cmd /k "cd frontend && npm run dev"
echo [완료] 프론트엔드 터미널 창을 열었습니다.
echo.

echo ===================================================
echo 모든 서버 실행 명령이 전달되었습니다! (새로 뜬 2개의 검은 창을 확인해 주세요)
echo 이 창은 5초 뒤에 자동으로 닫힙니다.
echo ===================================================
timeout /t 5 >nul
