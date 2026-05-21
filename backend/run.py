import sys
import os
import uvicorn

def main():
    """
    StockAuto FastAPI 통합 런처 (Spring Boot style Profile Launcher).
    구동 명령인자를 받아 OS 환경변수를 주입하고 Uvicorn 서버를 안전하게 기동합니다.
    
    사용 방법:
      - 로컬 개발 환경:  python run.py local  (또는 인자 생략 시 기본값)
      - 개발 서버 환경:  python run.py dev
      - 운영 실전 환경:  python run.py prod
    """
    # 1. 인자 분석 (기본값: local)
    profile = "local"
    valid_profiles = ("local", "dev", "prod")
    
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower().strip()
        if arg in valid_profiles:
            profile = arg
        else:
            print(f"[Launcher] ⚠️  알 수 없는 프로필인자 '{arg}'가 입력되었습니다. 기본값인 'local'로 진행합니다.")
            print(f"            (지원 가능 프로필: {', '.join(valid_profiles)})")
            
    # 2. 💡 프레임워크 로드 전 OS 환경변수 최우선 주입 (스프링부트 active.profile 역할)
    os.environ["APP_ENV"] = profile
    
    # 3. 환경별 Uvicorn 구동 파라미터 세팅
    host = "0.0.0.0"
    port = 8000
    is_local = (profile == "local")
    is_dev = (profile == "dev")
    
    # 로컬/개발 환경인 경우에만 자동 릴로드(Auto Reload) 활성화
    # 실전 운영(prod) 환경은 코드 자동저장으로 인한 서버 순간적 다운을 방지하기 위해 릴로드를 비활성화합니다.
    reload_enabled = is_local or is_dev
    
    # SQLite DB 락 방지 및 운영 서버 안정성을 위해 prod 모드에서는 단일 워커 프로세스로 고정합니다.
    workers_count = 1
    
    print("=" * 60)
    print(f"🚀  StockAuto 백엔드 서버를 기동합니다.  🚀")
    print(f"• 활성화된 프로필 (PROFILE):  {profile.upper()}")
    print(f"• 환경설정 파일 로드 타겟:    .env.{profile}")
    print(f"• 접속 주소 (Access URL):     http://{host}:{port}")
    print(f"• 소스코드 자동 릴로드:       {'활성화 (ON)' if reload_enabled else '비활성화 (OFF)'}")
    print("=" * 60)
    
    # 4. Uvicorn 구동
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        workers=workers_count,
        env_file=f".env.{profile}" # 💡 Uvicorn 레벨에서 단일 환경파일만 강제 주입하여 꼬임 방지
    )

if __name__ == "__main__":
    main()
