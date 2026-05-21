import sys
import os
import uvicorn

def bootstrap_venv():
    """
    [DX 업그레이드] 가상환경 자동 감지 및 프로세스 자가 치환 (Self Re-execution).
    현재 실행 중인 Python 인터프리터가 프로젝트 로컬 가상환경(venv) 내부의 것이 아니라면,
    경로 내의 'venv/Scripts/python.exe'를 찾아 프로세스를 스스로 대체(execv)시킵니다.
    이를 통해 터미널에서 가상환경 활성화(activate)를 생략해도 언제나 venv 모드로 무결하게 동작합니다.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # OS별 가상환경 내 파이썬 바이너리 경로 특정
    if os.name == "nt":  # Windows
        venv_python = os.path.join(current_dir, "venv", "Scripts", "python.exe")
    else:  # macOS / Linux
        venv_python = os.path.join(current_dir, "venv", "bin", "python")
        
    # 로컬 가상환경이 실제로 존재하고, 현재 프로세스가 해당 가상환경 파이썬이 아닌 경우
    if os.path.exists(venv_python) and os.path.abspath(sys.executable) != os.path.abspath(venv_python):
        print(f"[Launcher] [VENV DETECTED] 프로세스를 로컬 가상환경(venv) 파이썬으로 자가 재실행합니다...")
        # os.execv를 사용하여 현재 프로세스를 가상환경 파이썬 프로세스로 투명하게 대체
        # sys.argv 인자값도 손실 없이 완벽히 넘깁니다.
        try:
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
        workers=workers_count,
        env_file=f".env.{profile}" # Uvicorn 레벨에서 단일 환경파일만 강제 주입
    )

if __name__ == "__main__":
    main()
