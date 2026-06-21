#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
StockAuto verification harness.

This script is intentionally conservative:
- compile every backend Python file under backend/app
- run backend pytest scenario tests under backend/tests
- run frontend TypeScript, ESLint, and Playwright E2E checks

It should not call live broker or market data services. Tests that need external
systems must use fakes/mocks.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

CONTRACT_RECORD_HEADING = "### 변경 영향 기록"
CONTRACT_RECORD_FIELDS = (
    "변경 분류",
    "생산자",
    "소비자",
    "데이터 경계",
    "API 계약",
    "문서 반영",
    "회귀 테스트",
    "미해결 위험",
    "인수인계",
)
CONTRACT_EXACT_PATHS = {
    "AGENTS.md",
    "scripts/verify_harness.py",
    "backend/app/core/config.py",
    "backend/app/core/database.py",
    "backend/app/core/dependencies.py",
    "backend/app/core/exceptions.py",
    "backend/app/core/migrator.py",
    "backend/app/core/models.py",
    "backend/app/core/response.py",
    "backend/app/bot/order_reconciler.py",
    "backend/app/bot/scheduler.py",
    "backend/app/scanner/discovery.py",
    "backend/app/scanner/swing_prediction_cache.py",
    "frontend/lib/api.ts",
    "frontend/store/authStore.ts",
}


def safe_print(text: str = "") -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(text.encode(encoding, errors="replace").decode(encoding))


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def backend_python(root: Path) -> str:
    candidates = [
        root / "backend" / "venv" / "Scripts" / "python.exe",
        root / "backend" / "venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def print_banner() -> None:
    safe_print(f"{CYAN}{BOLD}")
    safe_print("=" * 65)
    safe_print("   [SHIELD] STOCKAUTO VERIFICATION HARNESS v1.3.0")
    safe_print("=" * 65)
    safe_print(f"{RESET}")


def run_command(
    command,
    *,
    cwd: Path,
    timeout: int = 120,
    env: dict[str, str] | None = None,
    shell: bool = False,
):
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def decode_changed_paths(result) -> list[str]:
    if result.returncode != 0:
        return []
    return [
        line.strip().replace("\\", "/")
        for line in result.stdout.decode("utf-8", errors="ignore").splitlines()
        if line.strip()
    ]


def get_changed_files(root: Path) -> list[str]:
    """Return the relevant change set for pre-commit, CI, or manual runs."""
    staged = decode_changed_paths(
        run_command(["git", "diff", "--cached", "--name-only"], cwd=root)
    )
    if staged:
        return sorted(set(staged))

    if os.environ.get("CI"):
        base_sha = os.environ.get("CHANGE_BASE_SHA", "").strip()
        if base_sha and set(base_sha) != {"0"}:
            ci_diff = decode_changed_paths(
                run_command(
                    ["git", "diff", "--name-only", f"{base_sha}...HEAD"],
                    cwd=root,
                )
            )
            if ci_diff:
                return sorted(set(ci_diff))

        head_diff = decode_changed_paths(
            run_command(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
                cwd=root,
            )
        )
        if head_diff:
            return sorted(set(head_diff))

    unstaged = decode_changed_paths(
        run_command(["git", "diff", "--name-only"], cwd=root)
    )
    untracked = decode_changed_paths(
        run_command(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=root,
        )
    )
    return sorted(set(unstaged + untracked))


def is_contract_sensitive(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized in CONTRACT_EXACT_PATHS:
        return True
    if normalized.startswith(".github/workflows/"):
        return True
    if normalized.startswith("backend/alembic/versions/"):
        return True
    if normalized.startswith("backend/app/scanner/") and normalized.endswith(".py"):
        return True
    if normalized.startswith("backend/app/"):
        filename = Path(normalized).name
        if filename.startswith("router") and filename.endswith(".py"):
            return True
    return False


def is_daily_task_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return bool(
        re.fullmatch(r"docs/tasks/\d{4}-\d{2}-\d{2}\.md", normalized)
    )


def find_complete_contract_record(content: str) -> tuple[bool, list[str], str]:
    if CONTRACT_RECORD_HEADING not in content:
        return False, list(CONTRACT_RECORD_FIELDS), ""

    sections = content.split(CONTRACT_RECORD_HEADING)[1:]
    best_missing = list(CONTRACT_RECORD_FIELDS)
    best_docs_value = ""
    for raw_section in sections:
        section = raw_section.split("\n## ", 1)[0]
        values: dict[str, str] = {}
        for line in section.splitlines():
            stripped = line.strip()
            for field in CONTRACT_RECORD_FIELDS:
                prefix = f"- {field}:"
                if stripped.startswith(prefix):
                    values[field] = stripped[len(prefix):].strip()

        missing = [
            field
            for field in CONTRACT_RECORD_FIELDS
            if not values.get(field)
            or values[field] in {"TODO", "TBD", "작성 필요"}
        ]
        if len(missing) < len(best_missing):
            best_missing = missing
            best_docs_value = values.get("문서 반영", "")
        if not missing:
            return True, [], values.get("문서 반영", "")

    return False, best_missing, best_docs_value


def validate_change_contract(root: Path, changed_files: list[str]) -> list[str]:
    sensitive_files = sorted(path for path in changed_files if is_contract_sensitive(path))
    if not sensitive_files:
        return []

    errors: list[str] = []
    task_paths = sorted(path for path in changed_files if is_daily_task_path(path))
    if not task_paths:
        return [
            "계약 영향 파일이 변경됐지만 docs/tasks/YYYY-MM-DD.md 변경이 없습니다.",
            f"영향 파일: {', '.join(sensitive_files)}",
        ]

    record_found = False
    missing_fields = list(CONTRACT_RECORD_FIELDS)
    docs_value = ""
    for task_path in reversed(task_paths):
        absolute_path = root / task_path
        if not absolute_path.exists():
            continue
        content = absolute_path.read_text(encoding="utf-8")
        complete, missing, candidate_docs_value = find_complete_contract_record(content)
        if complete:
            record_found = True
            docs_value = candidate_docs_value
            break
        if len(missing) < len(missing_fields):
            missing_fields = missing
            docs_value = candidate_docs_value

    if not record_found:
        errors.append(
            "일자별 현황판의 '### 변경 영향 기록'이 없거나 필수 항목이 비어 있습니다."
        )
        if missing_fields:
            errors.append(f"누락 항목: {', '.join(missing_fields)}")
        return errors

    long_lived_docs = [
        path
        for path in changed_files
        if path.startswith("docs/")
        and not path.startswith("docs/tasks/")
        and path.endswith(".md")
    ]
    if not long_lived_docs:
        no_impact_prefix = "영향 없음 -"
        if not docs_value.startswith(no_impact_prefix) or len(docs_value) <= len(no_impact_prefix) + 3:
            errors.append(
                "계약 영향 변경에는 docs/ 장기 문서 변경이 필요합니다. 영향이 없다면 "
                "'문서 반영: 영향 없음 - 구체적인 사유'를 기록하세요."
            )

    return errors


def check_change_contract(root: Path) -> bool:
    safe_print(f"{BOLD}[1/7] [CONTRACT] Change impact and handoff check...{RESET}")
    changed_files = get_changed_files(root)
    sensitive_files = [path for path in changed_files if is_contract_sensitive(path)]
    errors = validate_change_contract(root, changed_files)

    if errors:
        safe_print(f"  {RED}[FAIL] Change contract validation failed.{RESET}")
        for error in errors:
            safe_print(f"    - {error}")
        return False

    if sensitive_files:
        safe_print(
            f"  {GREEN}[OK] Change contract recorded for "
            f"{len(sensitive_files)} sensitive file(s).{RESET}\n"
        )
    else:
        safe_print(f"  {GREEN}[OK] No contract-sensitive changes detected.{RESET}\n")
    return True


def print_result_output(result) -> None:
    stdout = result.stdout.decode("utf-8", errors="ignore").strip()
    stderr = result.stderr.decode("utf-8", errors="ignore").strip()
    if stdout:
        safe_print(stdout)
    if stderr:
        safe_print(stderr)


def check_backend_compile(root: Path) -> bool:
    safe_print(f"{BOLD}[2/7] [BACKEND] Python compile check (Expanded)...{RESET}")
    backend_dir = root / "backend"
    python_exe = backend_python(root)
    failed_files: list[tuple[Path, str]] = []
    success_count = 0

    for file_path in backend_dir.rglob("*.py"):
        if "venv" in file_path.parts or ".pytest_cache" in file_path.parts or "__pycache__" in file_path.parts:
            continue
        result = run_command(
            [python_exe, "-m", "py_compile", str(file_path)],
            cwd=root,
            timeout=30,
        )
        if result.returncode != 0:
            failed_files.append((file_path, result.stderr.decode("utf-8", errors="ignore")))
        else:
            success_count += 1

    if failed_files:
        safe_print(f"  {RED}[FAIL] Backend compile failed for {len(failed_files)} file(s).{RESET}")
        for file_path, err in failed_files:
            safe_print(f"    - {file_path}")
            safe_print(err)
        return False

    safe_print(f"  {GREEN}[OK] Backend compile passed ({success_count} files).{RESET}\n")
    return True


def check_nfc_encoding(root: Path) -> bool:
    safe_print(f"{BOLD}[3/7] [CORE] NFC Encoding check (Korean)...{RESET}")
    failed_files = []
    import unicodedata
    
    result = run_command(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
    )
    if result.returncode != 0:
        safe_print(f"  {YELLOW}[WARN] git ls-files failed. Skipping NFC check.{RESET}\n")
        return True
        
    files = result.stdout.decode("utf-8", errors="ignore").splitlines()
    checked_count = 0
    for f in files:
        if f.endswith(('.py', '.md', '.tsx', '.ts')):
            file_path = root / f
            if not file_path.exists():
                continue
            try:
                content = file_path.read_text(encoding='utf-8')
                if not unicodedata.is_normalized('NFC', content):
                    failed_files.append(f)
                checked_count += 1
            except UnicodeDecodeError:
                pass
                
    if failed_files:
        safe_print(f"  {RED}[FAIL] NFC Encoding failed for {len(failed_files)} file(s).{RESET}")
        safe_print(f"  {RED}Please convert these files to NFC (e.g. using a normalization script).{RESET}")
        for f in failed_files:
            safe_print(f"    - {f}")
        return False

    safe_print(f"  {GREEN}[OK] NFC Encoding passed ({checked_count} files).{RESET}\n")
    return True


def check_alembic_migrations(root: Path) -> bool:
    safe_print(f"{BOLD}[4/7] [BACKEND] Alembic migrations check...{RESET}")
    backend_dir = root / "backend"
    python_exe = backend_python(root)
    
    # First, ensure DB is upgraded to head so check doesn't fail on missing tables
    run_command([python_exe, "-m", "alembic", "upgrade", "head"], cwd=backend_dir, timeout=60)
    
    # Run alembic check to find missing migrations
    result = run_command([python_exe, "-m", "alembic", "check"], cwd=backend_dir, timeout=60)
    
    if result.returncode != 0:
        safe_print(f"  {RED}[FAIL] Alembic check failed.{RESET}")
        safe_print(f"  {RED}Missing migrations detected! Did you forget to run 'alembic revision --autogenerate'?{RESET}")
        print_result_output(result)
        return False

    safe_print(f"  {GREEN}[OK] Alembic migrations are up to date.{RESET}\n")
    return True


def check_backend_tests(root: Path) -> bool:
    safe_print(f"{BOLD}[5/7] [BACKEND] pytest scenario harness...{RESET}")
    backend_dir = root / "backend"
    tests_dir = backend_dir / "tests"

    if not tests_dir.exists():
        safe_print(f"  {YELLOW}[WARN] backend/tests not found. Skipping pytest.{RESET}\n")
        return True

    env = os.environ.copy()
    env["PYTHONPATH"] = str(backend_dir) + os.pathsep + env.get("PYTHONPATH", "")
    result = run_command(
        [backend_python(root), "-m", "pytest"],
        cwd=backend_dir,
        timeout=120,
        env=env,
    )

    if result.returncode != 0:
        safe_print(f"  {RED}[FAIL] Backend pytest failed.{RESET}")
        print_result_output(result)
        return False

    print_result_output(result)
    safe_print(f"  {GREEN}[OK] Backend pytest passed.{RESET}\n")
    return True


def check_frontend_static(root: Path) -> bool:
    safe_print(f"{BOLD}[6/7] [FRONTEND] TypeScript and ESLint checks...{RESET}")
    frontend_dir = root / "frontend"

    if not frontend_dir.exists():
        safe_print(f"  {YELLOW}[WARN] frontend directory not found. Skipping frontend checks.{RESET}\n")
        return True

    safe_print("  * Running npx tsc --noEmit...")
    tsc_result = run_command("npx tsc --noEmit", cwd=frontend_dir, timeout=120, shell=True)

    safe_print("  * Running npm run lint...")
    lint_result = run_command("npm run lint", cwd=frontend_dir, timeout=120, shell=True)

    success = True
    if tsc_result.returncode != 0:
        safe_print(f"  {RED}[FAIL] TypeScript check failed.{RESET}")
        print_result_output(tsc_result)
        success = False

    if lint_result.returncode != 0:
        safe_print(f"  {RED}[FAIL] ESLint check failed.{RESET}")
        print_result_output(lint_result)
        success = False

    if success:
        safe_print(f"  {GREEN}[OK] Frontend checks passed.{RESET}\n")

    return success


def check_frontend_e2e(root: Path) -> bool:
    safe_print(f"{BOLD}[7/7] [FRONTEND] Playwright E2E smoke checks...{RESET}")
    frontend_dir = root / "frontend"
    playwright_config = frontend_dir / "playwright.config.ts"

    if not frontend_dir.exists():
        safe_print(f"  {YELLOW}[WARN] frontend directory not found. Skipping E2E checks.{RESET}\n")
        return True

    if not playwright_config.exists():
        safe_print(f"  {YELLOW}[WARN] Playwright config not found. Skipping E2E checks.{RESET}\n")
        return True

    result = run_command("npm run test:e2e", cwd=frontend_dir, timeout=180, shell=True)
    if result.returncode != 0:
        safe_print(f"  {RED}[FAIL] Playwright E2E failed.{RESET}")
        print_result_output(result)
        return False

    print_result_output(result)
    safe_print(f"  {GREEN}[OK] Playwright E2E passed.{RESET}\n")
    return True


def should_run_full_harness(root: Path) -> bool:
    """
    Check if full harness should run based on staged files.
    If only safe non-code files (like .md, .txt) are modified, skip heavy tests.
    """
    changed_files = get_changed_files(root)
    if not changed_files:
        return True # Not a git commit context (e.g., manual run), run full
        
    code_extensions = ('.py', '.ts', '.tsx', '.js', '.jsx', '.json', '.html', '.css')
    
    for f in changed_files:
        # If any file has a code extension or modifies core configs/migrations
        if f.endswith(code_extensions) or "alembic/" in f or "requirements" in f or "package" in f:
            return True
            
    # If we get here, only .md, .txt, .gitignore, etc. were found
    return False


def main() -> int:
    root = project_root()
    print_banner()

    run_full = should_run_full_harness(root)
    
    if run_full:
        checks = [
            check_change_contract,
            check_backend_compile,
            check_nfc_encoding,
            check_alembic_migrations,
            check_backend_tests,
            check_frontend_static,
            check_frontend_e2e,
        ]
    else:
        safe_print(f"  {YELLOW}[SMART SKIP] 단순 문서(Markdown 등) 수정만 감지되었습니다. 무거운 5가지 테스트를 건너뜁니다.{RESET}\n")
        checks = [
            check_change_contract,
            check_nfc_encoding, # 문서를 수정했어도 한글 자소 분리 방어선은 무조건 가동
        ]

    all_passed = True
    for check_func in checks:
        if not check_func(root):
            all_passed = False

    safe_print("=" * 65)
    if all_passed:
        safe_print(f"  {GREEN}{BOLD}[SUCCESS] Verification harness passed.{RESET}")
        safe_print("=" * 65)
        return 0

    safe_print(f"  {RED}{BOLD}[BLOCKED] Verification harness failed.{RESET}")
    safe_print("=" * 65)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
