import os
import sys
import zipfile
from datetime import datetime

# ANSI Color Codes for Premium Terminal UI
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Windows Command Prompt ANSI Support
if os.name == "nt":
    os.system("")

def print_banner():
    banner = f"""
{BLUE}{BOLD}============================================================
  🚀 StockAuto Trading Bridge - Safe Vault Backup & Restore
============================================================{RESET}
    """
    print(banner)

def get_backup_targets():
    """
    백업할 개인 파일 및 데이터베이스 목록을 정의합니다.
    (Git에 올라가지 않는 비공개 민감 설정 및 데이터베이스 파일들)
    """
    targets = [
        # Backend Files
        ("backend/.env.local", "backend/.env.local"),
        ("backend/.env.dev", "backend/.env.dev"),
        ("backend/.env.prod", "backend/.env.prod"),
        ("backend/stockauto.db", "backend/stockauto.db"),
        
        # Frontend Files
        ("frontend/.env.local", "frontend/.env.local"),
        ("frontend/.env.dev", "frontend/.env.dev"),
        ("frontend/.env.prod", "frontend/.env.prod"),
    ]
    return targets

def run_backup():
    print(f"{CYAN}[*] 개인 설정 및 데이터베이스 백업을 시작합니다...{RESET}\n")
    targets = get_backup_targets()
    
    # backups 폴더 생성
    backup_dir = "backups"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        print(f"📁 백업 디렉터리 생성 완료: {BOLD}./{backup_dir}{RESET}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"stockauto_backup_{timestamp}.zip"
    backup_filepath = os.path.join(backup_dir, backup_filename)

    backed_up_files = []
    missing_files = []

    try:
        with zipfile.ZipFile(backup_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path, arc_name in targets:
                if os.path.exists(file_path):
                    zipf.write(file_path, arc_name)
                    file_size = os.path.getsize(file_path)
                    print(f"  {GREEN}✓{RESET} {file_path:<25} 백업 완료 ({file_size:,} bytes)")
                    backed_up_files.append(file_path)
                else:
                    missing_files.append(file_path)

        if not backed_up_files:
            print(f"\n{RED}❌ 백업할 수 있는 대상 파일이 존재하지 않습니다.{RESET}")
            if os.path.exists(backup_filepath):
                os.remove(backup_filepath)
            return

        print(f"\n{GREEN}{BOLD}============================================================{RESET}")
        print(f"{GREEN}🎉 백업 패키지가 성공적으로 생성되었습니다!{RESET}")
        print(f"💾 백업 파일: {YELLOW}{BOLD}{backup_filepath}{RESET}")
        print(f"📊 백업 완료: {len(backed_up_files)}개 파일 | 누락: {len(missing_files)}개 파일")
        if missing_files:
            print(f"{YELLOW}⚠️  누락된 파일 (미생성 상태):{RESET} {', '.join(missing_files)}")
        print(f"{GREEN}{BOLD}============================================================{RESET}")
        print(f"{CYAN}💡 [팁] 이 ZIP 파일 하나만 외부 이메일, 클라우드(OneDrive, Google Drive) 또는{RESET}")
        print(f"{CYAN}       개인 USB에 보관하시면 PC 포맷 시에도 1초 만에 복구할 수 있습니다.{RESET}")

    except Exception as e:
        print(f"\n{RED}❌ 백업 중 치명적인 오류가 발생했습니다: {e}{RESET}")

def run_restore(backup_file):
    if not os.path.exists(backup_file):
        print(f"{RED}❌ 백업 파일을 찾을 수 없습니다: {backup_file}{RESET}")
        return

    print(f"\n{YELLOW}{BOLD}⚠️ [경고] 복구를 진행하면 현재 로컬의 모든 .env 파일과 stockauto.db가{RESET}")
    print(f"{YELLOW}{BOLD}          백업 파일의 내용으로 완전히 덮어씌워집니다!{RESET}")
    confirm = input(f"{YELLOW}정말 복구를 진행하시겠습니까? (y/n): {RESET}").strip().lower()
    
    if confirm != 'y':
        print(f"\n{BLUE}[*] 복구 작업이 사용자에 의해 취소되었습니다.{RESET}")
        return

    print(f"\n{CYAN}[*] 백업 파일 분석 및 복구를 개시합니다...{RESET}\n")

    try:
        with zipfile.ZipFile(backup_file, 'r') as zipf:
            namelist = zipf.namelist()
            print(f"📦 백업 패키지 내부 파일 목록 ({len(namelist)}개):")
            for name in namelist:
                print(f"  - {name}")
            print()

            # 압축 해제 실행
            zipf.extractall()
            
        print(f"{GREEN}{BOLD}============================================================{RESET}")
        print(f"{GREEN}🎉 모든 설정 및 데이터베이스 복구가 완료되었습니다!{RESET}")
        print(f"✨ 이제 가상환경을 활성화한 후 서버 및 프론트엔드를 실행하시면 됩니다.{RESET}")
        print(f"{GREEN}{BOLD}============================================================{RESET}")

    except Exception as e:
        print(f"{RED}❌ 복구 중 치명적인 오류가 발생했습니다: {e}{RESET}")

def main():
    print_banner()
    
    if len(sys.argv) > 1 and sys.argv[1].lower() == "restore":
        if len(sys.argv) < 3:
            # 가장 최신 백업 파일 찾기
            backup_dir = "backups"
            if os.path.exists(backup_dir):
                backups = [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.endswith(".zip")]
                if backups:
                    latest_backup = max(backups, key=os.path.getctime)
                    run_restore(latest_backup)
                    return
            
            print(f"{RED}❌ 복구할 백업 파일명을 입력해 주세요.{RESET}")
            print(f"💡 사용법: {BOLD}python backup.py restore <backup_filepath>{RESET}")
            print(f"💡 예  시: {BOLD}python backup.py restore backups/stockauto_backup_20260524_170000.zip{RESET}")
        else:
            run_restore(sys.argv[2])
    else:
        run_backup()

if __name__ == "__main__":
    main()
