# -*- coding: utf-8 -*-
"""전략별 라이브 진입 상태 스냅샷 갱신기.

`backend/tests/strategy_entry_states.json`을 다시 굽는다. 이 스냅샷은
`test_strategy_entry_states_match_the_snapshot`이 목록 차분으로 검사하며,
차분이 생기면 반드시 사람이 사유를 판단하도록 강제하는 것이 목적이다.

왜 종수 임계값이 아니라 목록인가:
  2026-08-23 실측에서 조건 퇴화 3종을 차단하는 **정당한 수정**이 미진입 종수를
  73에서 76으로 늘렸다. "미진입 <= N이면 통과" 방식은 이 수정을 회귀로 오판한다.
  반대로 종수가 같아도 구성이 바뀔 수 있다(퇴화 3종이 부활 3종으로 교체된 사례).

사용법:
    python scripts/update_strategy_entry_states.py

갱신 후에는 diff를 눈으로 확인하고, 바뀐 사유를 당일 현황판의
`### 변경 영향 기록`에 남긴다. 사유 없이 갱신하면 이 가드는 무의미해진다.
"""

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "backend" / "tests" / "strategy_entry_states.json"

# 상태 판정 로직은 테스트 파일이 단독 소유한다(SSOT). 여기서 다시 구현하면
# 스냅샷과 검사가 서로 다른 기준을 쓰게 되어 가드가 조용히 무력해진다.
_COLLECT = """
import json, sys
sys.path.insert(0, "tests")
from test_live_entry_signal_contract import current_entry_states, _exit_unresponsive
payload = {"states": current_entry_states(),
           "exit_unresponsive": _exit_unresponsive()}
print("<<<STATES>>>" + json.dumps(payload, ensure_ascii=False))
"""


def _python_executable() -> str:
    """백엔드 venv의 인터프리터를 우선 쓴다(시스템 python에는 의존성이 없다)."""
    venv = ROOT / "backend" / "venv" / "Scripts" / "python.exe"
    return str(venv) if venv.exists() else sys.executable


def main() -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "backend")
    result = subprocess.run(
        [_python_executable(), "-c", _COLLECT],
        cwd=str(ROOT / "backend"),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout or "")
        sys.stderr.write(result.stderr or "")
        print("[FAIL] 상태 수집에 실패했습니다.")
        return 1

    marker = "<<<STATES>>>"
    line = next(
        (ln for ln in (result.stdout or "").splitlines() if ln.startswith(marker)),
        None,
    )
    if line is None:
        sys.stderr.write(result.stdout or "")
        print("[FAIL] 상태 출력을 찾지 못했습니다.")
        return 1
    collected = json.loads(line[len(marker):])
    states = collected["states"]
    exit_stuck = collected["exit_unresponsive"]

    previous = {}
    if SNAPSHOT.exists():
        previous = json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("states", {})

    payload = {
        "_comment": (
            "전략별 라이브 진입 상태 스냅샷. 손으로 고치지 말고 "
            "python scripts/update_strategy_entry_states.py 로 갱신할 것. "
            "차분이 생기면 사유를 당일 현황판 변경 영향 기록에 남긴다."
        ),
        "updated_at": date.today().isoformat(),
        "states": dict(sorted(states.items())),
        "exit_unresponsive": sorted(exit_stuck),
    }
    SNAPSHOT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    added = sorted(set(states) - set(previous))
    removed = sorted(set(previous) - set(states))
    changed = sorted(
        f"{name}: {previous[name]} -> {states[name]}"
        for name in set(previous) & set(states)
        if previous[name] != states[name]
    )
    counts = {}
    for state in states.values():
        counts[state] = counts.get(state, 0) + 1

    print(f"[OK] 스냅샷 갱신: {SNAPSHOT.relative_to(ROOT)} ({len(states)}종)")
    print(f"     시그널 청산 불가: {len(exit_stuck)}종")
    for state, count in sorted(counts.items()):
        print(f"     {state}: {count}")
    if added:
        print(f"     신규: {', '.join(added)}")
    if removed:
        print(f"     제거: {', '.join(removed)}")
    if changed:
        print("     상태 변경:")
        for item in changed:
            print(f"       - {item}")
    if not (added or removed or changed) and previous:
        print("     변경 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
