#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
StockAuto AI 에이전트 하드 하네스 검증기 (Hard Harness Verifier)
이 스크립트는 백엔드 컴파일 무결성과 프론트엔드 TypeScript/Lint 무결성을 
자동으로 검사하여 실패 시 에러를 뿜으며 커밋 및 병합을 물리적으로 원천 차단합니다.
"""

import sys
import os
import subprocess

# Windows cmd.exe의 경우 컬러 인코딩 에러 방지를 위해 표준 출력 설정 지원
try:
    if os.name == 'nt':
        os.system('color')
except Exception:
    pass

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

# 윈도우 인코딩(CP949 등) 환경에서 이모지 출력 시 에러가 나는 것을 방지하기 위해 표준 기호 사용
EMOJI_SHIELD = "[SHIELD]"
EMOJI_BE = "[BACKEND]"
EMOJI_FE = "[FRONTEND]"
EMOJI_CHECK = "[OK]"
EMOJI_FAIL = "[FAIL]"
EMOJI_WARNING = "[WARNING]"
EMOJI_CONGRATS = "[SUCCESS]"

def safe_print(text):
    """윈도우 콘솔 인코딩(CP949 등)에서 출력 불가능한 특수 문자가 있을 때 크래시를 방지하는 안전 출력 함수"""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or 'utf-8'
        # 인코딩할 수 없는 문자는 대체문자('?')로 치환하여 안전하게 출력
        clean_text = text.encode(encoding, errors='replace').decode(encoding)
        print(clean_text)

def print_banner():
    safe_print(f"{CYAN}{BOLD}")
    safe_print("=" * 65)
    safe_print(f"   {EMOJI_SHIELD}  STOCKAUTO HARD HARNESS ENVIRONMENTAL VERIFIER v1.0.0")
    safe_print("=" * 65)
    safe_print(f"{RESET}")

def check_backend(project_root):
    safe_print(f"{BOLD}[1/2] {EMOJI_BE} 백엔드 문법 및 컴파일 무결성 검증 개시...{RESET}")
    backend_app_dir = os.path.join(project_root, "backend", "app")
    
    # backend/app 하위의 모든 .py 파일 검색 및 컴파일
    failed_files = []
    success_count = 0
    
    for root, _, files in os.walk(backend_app_dir):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                # python -m py_compile 실행
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", file_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                if result.returncode != 0:
                    failed_files.append((file, result.stderr.decode("utf-8", errors="ignore")))
                else:
                    success_count += 1

    if failed_files:
        safe_print(f"  {RED}{EMOJI_FAIL} 백엔드 무결성 검증 실패! ({len(failed_files)}개 파일 오류){RESET}")
        for file, err in failed_files:
            safe_print(f"    - {RED}{file} 컴파일 에러:{RESET}\n{err}")
        return False
    
    safe_print(f"  {GREEN}{EMOJI_CHECK} 백엔드 컴파일 무결성 통과! (총 {success_count}개 파일 완료){RESET}\n")
    return True

def check_frontend(project_root):
    safe_print(f"{BOLD}[2/2] {EMOJI_FE} 프론트엔드 TypeScript 및 린트 검증 개시...{RESET}")
    frontend_dir = os.path.join(project_root, "frontend")
    
    if not os.path.exists(frontend_dir):
        safe_print(f"  {YELLOW}{EMOJI_WARNING} 프론트엔드 디렉터리를 찾을 수 없습니다. 건너뜁니다.{RESET}\n")
        return True

    # 1. TypeScript 타입 검사 (npx tsc --noEmit)
    safe_print("  * TypeScript 타입 무결성 검사 중 (npx tsc --noEmit)...")
    tsc_result = subprocess.run(
        "npx tsc --noEmit",
        shell=True,
        cwd=frontend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # 2. ESLint 린트 검사 (npm run lint)
    safe_print("  * ESLint 정적 코드 분석 검사 중 (npm run lint)...")
    lint_result = subprocess.run(
        "npm run lint",
        shell=True,
        cwd=frontend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    success = True
    if tsc_result.returncode != 0:
        safe_print(f"  {RED}{EMOJI_FAIL} TypeScript 타입 체크 실패!{RESET}")
        safe_print(tsc_result.stdout.decode("utf-8", errors="ignore"))
        safe_print(tsc_result.stderr.decode("utf-8", errors="ignore"))
        success = False

    if lint_result.returncode != 0:
        safe_print(f"  {RED}{EMOJI_FAIL} ESLint 린트 검사 실패!{RESET}")
        safe_print(lint_result.stdout.decode("utf-8", errors="ignore"))
        safe_print(lint_result.stderr.decode("utf-8", errors="ignore"))
        success = False

    if success:
        safe_print(f"  {GREEN}{EMOJI_CHECK} 프론트엔드 타입 및 린트 무결성 통과!{RESET}\n")
    
    return success

def main():
    print_banner()
    
    # 프로젝트 루트 구하기 (이 파일이 scripts/ 하위에 위치하므로 부모 디렉터리)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    be_pass = check_backend(project_root)
    fe_pass = check_frontend(project_root)
    
    safe_print("=" * 65)
    if be_pass and fe_pass:
        safe_print(f"  {GREEN}{BOLD}{EMOJI_CONGRATS} [SUCCESS] 모든 하드 하네스 보안 가드라인 통과!{RESET}")
        safe_print(f"  {GREEN}코드 무결성이 완벽하게 증명되었습니다. 커밋/배포가 허용됩니다.{RESET}")
        safe_print("=" * 65)
        sys.exit(0)
    else:
        safe_print(f"  {RED}{BOLD}{EMOJI_FAIL} [BLOCKED] 하드 하네스 검증 통과 실패!{RESET}")
        safe_print(f"  {RED}린트 또는 컴파일 결함이 존재합니다. 수정 후 다시 시도하십시오.{RESET}")
        safe_print("=" * 65)
        sys.exit(1)

if __name__ == "__main__":
    main()
