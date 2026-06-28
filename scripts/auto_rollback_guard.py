#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auto-Rollback Guard for StockAuto Release Harness.

Provides automated workspace safety checks, change snapshots, and rollback mechanisms
to prevent corrupted edits from polluting the repository when verification harness checks fail.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def run_git_command(args: list[str], root: Path) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Git command failed: git {' '.join(args)}\nError: {result.stderr}")
    return result.stdout.strip()


def check_rollback_safety_status(root: Path) -> dict[str, int]:
    """Inspect current unstaged and untracked changes for rollback safety."""
    status_output = run_git_command(["status", "--porcelain"], root)
    lines = [line for line in status_output.splitlines() if line.strip()]
    
    modified = sum(1 for line in lines if line.startswith(" M") or line.startswith("M "))
    untracked = sum(1 for line in lines if line.startswith("??"))
    staged = sum(1 for line in lines if line.startswith("A ") or line.startswith("M "))
    
    return {
        "modified": modified,
        "untracked": untracked,
        "staged": staged,
        "total_changes": len(lines),
    }


def perform_safe_rollback(root: Path, hard: bool = False) -> None:
    """Execute workspace rollback to ensure code safety."""
    print(f"[ROLLBACK GUARD] Executing workspace cleanup (hard={hard})...")
    if hard:
        run_git_command(["reset", "--hard", "HEAD"], root)
        print("[ROLLBACK GUARD] Workspace reverted to HEAD successfully.")
    else:
        print("[ROLLBACK GUARD] Dry-run check completed. Use --hard to force revert.")


if __name__ == "__main__":
    root_dir = project_root()
    if "--hard" in sys.argv:
        try:
            perform_safe_rollback(root_dir, hard=True)
            sys.exit(0)
        except Exception as exc:
            print(f"[ERROR] Auto-Rollback failed: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            status = check_rollback_safety_status(root_dir)
            print(f"[ROLLBACK GUARD] Active workspace changes: {status['total_changes']} files modified/untracked.")
            print("[ROLLBACK GUARD] Rollback guard is active and operational.")
            sys.exit(0)
        except Exception as exc:
            print(f"[ERROR] Rollback guard check failed: {exc}", file=sys.stderr)
            sys.exit(1)
