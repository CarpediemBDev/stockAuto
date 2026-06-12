import sys
import os
import multiprocessing
import uvicorn

OFFICIAL_VENV_DIR = "venv"

def bootstrap_venv():
    """
    [DX 업그레이드] 가상환경 자동 감지 및 프로세스 자가 치환 (Self Re-execution).
    StockAuto의 공식 백엔드 가상환경 디렉터리는 backend/venv 입니다.
    현재 실행 중인 Python 인터프리터가 공식 로컬 가상환경(venv) 내부의 것이 아니라면,
    backend/venv 아래의 Python 실행 파일을 찾아 프로세스를 스스로 대체(execv)시킵니다.
    이를 통해 터미널에서 가상환경 활성화(activate)를 생략해도 언제나 backend/venv 기준으로 동작합니다.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # OS별 가상환경 내 파이썬 바이너리 경로 특정
    if os.name == "nt":  # Windows
        venv_python = os.path.join(current_dir, OFFICIAL_VENV_DIR, "Scripts", "python.exe")
    else:  # macOS / Linux
        venv_python = os.path.join(current_dir, OFFICIAL_VENV_DIR, "bin", "python")
        
    # 로컬 가상환경이 실제로 존재하고, 현재 프로세스가 해당 가상환경 파이썬이 아닌 경우
    if os.path.exists(venv_python) and os.path.abspath(sys.executable) != os.path.abspath(venv_python):
        print(f"[Launcher] [VENV DETECTED] 프로세스를 공식 백엔드 가상환경(backend/venv) 파이썬으로 자가 재실행합니다...")
        try:
            if os.name == "nt":
                # Windows 환경에서는 os.execv 호출 시 백그라운드로 자식 프로세스가 고아(Orphan)로 방치되는 문제를 예방하기 위해,
                # subprocess로 자식을 실행하고 KeyboardInterrupt(Ctrl+C) 신호를 자식에게 포워딩합니다.
                import subprocess
                p = subprocess.Popen([venv_python] + sys.argv)
                try:
                    p.wait()
                except KeyboardInterrupt:
                    p.terminate()
                    p.wait()
                sys.exit(p.returncode)
            else:
                # Unix/Mac 환경에서는 기존대로 네이티브 os.execv로 프로세스 자가를 깔끔히 치환합니다.
                os.execv(venv_python, [venv_python] + sys.argv)
        except Exception as e:
            print(f"[Launcher] ⚠️ 가상환경 자가 전환 중 실패했습니다. 수동으로 가상환경을 활성화해 주세요. (Error: {e})")

# 💡 Uvicorn 로드 및 프레임워크 로딩 전 최우선적으로 가상환경 치환 수행
bootstrap_venv()

def main():
    """
    StockAuto FastAPI 통합 런처 (Spring Boot style Profile Launcher).
    구동 명령인자를 받아 OS 환경변수를 주입하고 Uvicorn 서버를 안전하게 기동합니다.
    """
    # 1. 인자 분석 (기본값: local)
    profile = "local"
    valid_profiles = ("local", "dev", "prod")
    
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower().strip()
        if arg in valid_profiles:
            profile = arg
        else:
            print(f"[Launcher] [WARNING] unknown profile '{arg}' was inputted. Proceeding with 'local'.")
            print(f"            (Profiles: {', '.join(valid_profiles)})")
            
    # 2. 💡 프레임워크 로드 전 OS 환경변수 최우선 주입 (스프링부트 active.profile 역할)
    os.environ["APP_ENV"] = profile
    backend_dir = os.path.dirname(os.path.abspath(__file__))

    # Windows의 Uvicorn reload 자식 프로세스도 공식 backend/venv Python을 사용하도록 고정합니다.
    multiprocessing.set_executable(sys.executable)
    
    # 3. 환경별 Uvicorn 구동 파라미터 세팅
    host = "0.0.0.0"
    port = 8000
    is_local = (profile == "local")
    is_dev = (profile == "dev")
    
    # 로컬/개발 환경인 경우에만 자동 릴로드(Auto Reload) 활성화
    reload_enabled = is_local or is_dev
    
    # SQLite DB 락 방지 및 운영 서버 안정성을 위해 prod 모드에서는 단일 워커 프로세스로 고정합니다.
    workers_count = 1
    
    print("=" * 60)
    print(f"[*] Starting StockAuto Backend Server...")
    print(f" PROFILE:  {profile.upper()}")
    print(f" ENV FILE: .env.{profile}")
    print(f" URL:      http://{host}:{port}")
    print(f" RELOAD:   {'ON' if reload_enabled else 'OFF'}")
    print("=" * 60)
    
    # 4. Uvicorn 구동
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        reload_dirs=[os.path.join(backend_dir, "app")] if reload_enabled else None,
        reload_excludes=["*.db", "*.db-journal", "*.sqlite3", "venv/*", "__pycache__/*", "logs/*", "*.log", "backend/logs/*", "**/logs/*", "**/*.log"],
        workers=workers_count,
        env_file=f".env.{profile}" # Uvicorn 레벨에서 단일 환경파일만 강제 주입
    )

if __name__ == "__main__":
    main()
