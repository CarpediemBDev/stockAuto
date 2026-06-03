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
import subprocess
import sys
from pathlib import Path


GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


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
    safe_print("   [SHIELD] STOCKAUTO VERIFICATION HARNESS v1.2.0")
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


def print_result_output(result) -> None:
    stdout = result.stdout.decode("utf-8", errors="ignore").strip()
    stderr = result.stderr.decode("utf-8", errors="ignore").strip()
    if stdout:
        safe_print(stdout)
    if stderr:
        safe_print(stderr)


def check_backend_compile(root: Path) -> bool:
    safe_print(f"{BOLD}[1/4] [BACKEND] Python compile check...{RESET}")
    app_dir = root / "backend" / "app"
    python_exe = backend_python(root)
    failed_files: list[tuple[Path, str]] = []
    success_count = 0

    for file_path in app_dir.rglob("*.py"):
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


def check_backend_tests(root: Path) -> bool:
    safe_print(f"{BOLD}[2/4] [BACKEND] pytest scenario harness...{RESET}")
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
    safe_print(f"{BOLD}[3/4] [FRONTEND] TypeScript and ESLint checks...{RESET}")
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
    safe_print(f"{BOLD}[4/4] [FRONTEND] Playwright E2E smoke checks...{RESET}")
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


def main() -> int:
    root = project_root()
    print_banner()

    backend_compile_pass = check_backend_compile(root)
    backend_tests_pass = check_backend_tests(root)
    frontend_static_pass = check_frontend_static(root)
    frontend_e2e_pass = check_frontend_e2e(root)

    safe_print("=" * 65)
    if backend_compile_pass and backend_tests_pass and frontend_static_pass and frontend_e2e_pass:
        safe_print(f"  {GREEN}{BOLD}[SUCCESS] Verification harness passed.{RESET}")
        safe_print("=" * 65)
        return 0

    safe_print(f"  {RED}{BOLD}[BLOCKED] Verification harness failed.{RESET}")
    safe_print("=" * 65)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
