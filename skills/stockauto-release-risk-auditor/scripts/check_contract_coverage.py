#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def require_file(root: Path, relative: str, errors: list[str]) -> str:
    path = root / relative
    if not path.exists():
        errors.append(f"{relative} is missing")
        return ""
    return path.read_text(encoding="utf-8")


def require_contains(text: str, needle: str, label: str, errors: list[str]) -> None:
    if needle not in text:
        errors.append(f"{label} missing required marker: {needle}")


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    errors: list[str] = []

    scanner_router_test = require_file(root, "backend/tests/test_scanner_router.py", errors)
    scanner_multitenancy = require_file(root, "backend/tests/test_scanner_multitenancy.py", errors)
    after_hours_scanner = require_file(root, "backend/app/scanner/after_hours_scanner.py", errors)
    release_artifacts = require_file(root, "backend/tests/test_release_artifacts.py", errors)
    verify_harness = require_file(root, "scripts/verify_harness.py", errors)
    daily_dir = root / "docs" / "tasks"

    require_contains(scanner_router_test, "after-hours-candidates", "scanner router tests", errors)
    require_contains(scanner_router_test, "auto-learn translations", "scanner router tests", errors)
    require_contains(scanner_router_test, "fresh_cache_cooldown", "scanner router tests", errors)
    require_contains(after_hours_scanner, "translate_cached", "after-hours scanner", errors)
    require_contains(scanner_multitenancy, "swing-predict", "scanner multitenancy tests", errors)
    require_contains(release_artifacts, "APP_ENV=prod", "release artifact tests", errors)
    require_contains(verify_harness, "Change impact", "verify harness", errors)

    if daily_dir.exists():
        latest = sorted(daily_dir.glob("20*.md"))[-1:]
        if latest:
            latest_text = latest[0].read_text(encoding="utf-8")
            require_contains(latest_text, "변경 영향 기록", f"{latest[0].name}", errors)
    else:
        errors.append("docs/tasks directory is missing")

    if errors:
        print("Contract coverage check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Contract coverage check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
