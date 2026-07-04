"""일자별 현황판(docs/tasks/YYYY-MM-DD.md) 스캐폴딩 도구.

AGENTS.md와 verify_harness.py가 요구하는 '### 변경 영향 기록' 규격을
AI/개발자가 매번 수기로 맞추다 형식 오류를 내는 문제를 없애기 위해,
당일 현황판을 표준 템플릿으로 자동 생성한다.

사용법:
    python scripts/new_task.py                 # 오늘 날짜 현황판 생성/점검
    python scripts/new_task.py 2026-07-05      # 특정 날짜 지정
    python scripts/new_task.py --title "관심종목 손익 SSOT 정리"

이미 파일이 있으면 절대 덮어쓰지 않고, 누락된 '### 변경 영향 기록' 블록만
안전하게 append 한다. 필드 목록은 verify_harness.py를 단일 기준(SSOT)으로 import 한다.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# 계약 규격 SSOT: verify_harness가 실제로 검사하는 값을 그대로 사용한다.
from verify_harness import CONTRACT_RECORD_FIELDS, CONTRACT_RECORD_HEADING  # noqa: E402

TASKS_DIR = ROOT / "docs" / "tasks"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def build_contract_block() -> str:
    """verify_harness가 인식하는 정확한 '- 필드: ' 형식으로 빈 기록 블록을 만든다."""
    lines = [CONTRACT_RECORD_HEADING]
    for field in CONTRACT_RECORD_FIELDS:
        lines.append(f"- {field}: ")
    lines.append("")
    lines.append(
        "> ⚠️ 위 9개 필드를 모두 채워야 verify_harness의 계약 검사를 통과합니다. "
        "(형식 고정: `- 필드명: 내용`, 별표/볼드 금지)"
    )
    return "\n".join(lines) + "\n"


def build_new_board(day: str, title: str) -> str:
    return (
        f"# {day} Task Board\n\n"
        f"## {title}\n"
        "- [ ] (작업을 선등록하세요. 상태: [ ] 대기 / [/] 진행 / [R] 검증완료·승인대기 / [x] 승인 / [-] 취소)\n\n"
        f"{build_contract_block()}"
    )


def ensure_board(day: str, title: str) -> tuple[Path, str]:
    """현황판을 생성하거나, 기존 파일에 계약 블록만 보강한다. (덮어쓰기 없음)"""
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    path = TASKS_DIR / f"{day}.md"

    if not path.exists():
        path.write_text(build_new_board(day, title), encoding="utf-8")
        return path, "created"

    content = path.read_text(encoding="utf-8")
    if CONTRACT_RECORD_HEADING in content:
        return path, "exists"

    # 기존 파일 보존 + 계약 블록만 안전하게 덧붙임
    suffix = "" if content.endswith("\n") else "\n"
    path.write_text(content + suffix + "\n" + build_contract_block(), encoding="utf-8")
    return path, "appended"


def main() -> int:
    parser = argparse.ArgumentParser(description="일자별 현황판 스캐폴딩")
    parser.add_argument(
        "day",
        nargs="?",
        default=date.today().isoformat(),
        help="YYYY-MM-DD (기본값: 오늘)",
    )
    parser.add_argument(
        "--title",
        default="신규 작업",
        help="현황판 최상단 작업 섹션 제목",
    )
    args = parser.parse_args()

    if not DATE_RE.match(args.day):
        print(f"[ERROR] 날짜 형식이 잘못됐습니다: {args.day} (YYYY-MM-DD 필요)")
        return 2
    try:
        datetime.strptime(args.day, "%Y-%m-%d")
    except ValueError:
        print(f"[ERROR] 존재하지 않는 날짜입니다: {args.day}")
        return 2

    path, status = ensure_board(args.day, args.title)
    rel = path.relative_to(ROOT).as_posix()
    messages = {
        "created": f"[OK] 신규 현황판 생성: {rel}",
        "appended": f"[OK] 기존 현황판에 '{CONTRACT_RECORD_HEADING}' 블록 보강: {rel}",
        "exists": f"[SKIP] 이미 계약 블록이 존재합니다: {rel}",
    }
    print(messages[status])
    if status != "exists":
        print("  → 9개 필드를 채운 뒤 python scripts/verify_harness.py 로 검증하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
