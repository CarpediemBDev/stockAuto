#!/usr/bin/env python
"""PreToolUse guard: 살아있는 Next 서버 밑의 dist 디렉터리(.next / .next-e2e) 삭제 차단.

2026-09-08 사고: 다른 세션이 하네스 실행 전 청소 목적으로
`cd frontend && rm -rf .next` 를 돌렸는데, 그 시점에 `npm run local`(next dev)
서버가 살아 있었다. 1차 rm 은 `.next/dev/cache/turbopack/ee6e79b1: Directory not
empty` 로 실패했고(서버가 핸들을 쥔 채 캐시를 재생성 중), 2차 rm 이 에러를
무시하고 지워버렸다. 서버는 죽지 않았으므로 메모리에 올라간 Turbopack 색인은
사라진 `.sst` 조각을 계속 참조했고, 이후 모든 요청이
`Unable to open static sorted file ... (os error 3)` 로 깨졌다.

핵심은 '캐시 손상'이 아니라 '서버는 살아있는데 그 밑의 캐시만 삭제된 불일치'라는
점이다. 그래서 dist 삭제 자체를 막지 않고, **그 dist 를 점유한 Next 서버가 살아
있을 때만** 차단한다. 서버가 없으면 캐시 청소는 정상 작업이므로 통과시킨다.

동작:
- 명령 텍스트에서 삭제 대상 dist(.next / .next-e2e)를 판별한다. git clean 은
  둘 다 지우므로 둘 다 대상으로 본다.
- 해당 dist 를 점유한 이 저장소의 Next 서버 프로세스를 찾는다.
  (cmdline 에 `.next-e2e` 가 있으면 E2E 서버, 없으면 dev 서버가 `.next` 점유)
- 살아 있으면 deny + 종료할 PID 와 명령을 알려준다. 없으면 통과.

실패는 항상 fail-open(통과)이다. 가드가 개발을 막아서는 안 된다.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

DEV_DIST = ".next"
E2E_DIST = ".next-e2e"

# 삭제 계열 동사. 이게 없으면 단순 조회/빌드이므로 관심 없다.
DELETE_VERB = re.compile(
    r"(\brm\b|\brmdir\b|\brd\b|\bdel\b|\berase\b|rimraf|"
    r"Remove-Item|shutil\.rmtree|os\.rmdir|fs\.rm|"
    r"\bgit\s+clean\b)",
    re.IGNORECASE,
)
# git clean 은 untracked 를 쓸어담으므로 dist 이름이 명시되지 않아도 둘 다 지운다.
GIT_CLEAN = re.compile(r"\bgit\s+clean\b[^\n]*-[a-z]*[xd]", re.IGNORECASE)
# `.next-e2e` 를 `.next` 로 오인하지 않도록 뒤에 이름 글자가 오면 제외한다.
DEV_DIST_REF = re.compile(r"\.next(?![\w.-])", re.IGNORECASE)
E2E_DIST_REF = re.compile(r"\.next-e2e(?![\w.-])", re.IGNORECASE)


# 커밋 메시지처럼 '명령'이 아니라 '문장'을 실어 나르는 명령은 예외로 둔다.
# 2026-09-09 실제 오탐: 위 사고 경위를 그대로 적은 커밋 메시지에 rm 과 .next 가
# 함께 등장한다는 이유로 커밋 자체가 거부됐다. 체이닝 연산자가 하나도 없는 단일
# 명령일 때만 예외이므로 `git commit -m "..." && rm -rf .next` 같은 우회는 그대로
# 걸린다.
MESSAGE_BEARING = re.compile(
    r"^\s*(git\s+(commit|tag)|gh\s+(pr|issue|release))\b", re.IGNORECASE
)
CHAINING = re.compile(r"&&|\|\||;|\|")


def is_message_bearing(command: str) -> bool:
    return bool(MESSAGE_BEARING.match(command)) and not CHAINING.search(command)


def targeted_dists(command: str) -> set[str]:
    if is_message_bearing(command):
        return set()
    if GIT_CLEAN.search(command):
        return {DEV_DIST, E2E_DIST}
    if not DELETE_VERB.search(command):
        return set()
    targets = set()
    if E2E_DIST_REF.search(command):
        targets.add(E2E_DIST)
    if DEV_DIST_REF.search(command):
        targets.add(DEV_DIST)
    return targets


def next_servers() -> list[tuple[int, str]]:
    """이 저장소 frontend 를 서빙 중인 node 프로세스 목록. 조회 실패 시 빈 목록."""
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
        rows = json.loads(out) if out else []
    except Exception:
        return []
    if isinstance(rows, dict):
        rows = [rows]

    frontend_key = str(FRONTEND).replace("\\", "/").lower()
    found = []
    for row in rows:
        cmdline = (row or {}).get("CommandLine") or ""
        norm = cmdline.replace("\\", "/").lower()
        if frontend_key not in norm:
            continue
        if "next" not in norm:
            continue
        # dev 컴파일 워커(.next/dev/build/postcss.js 등)는 서버가 아니라 서버의
        # 자식이다. 부모를 /T 로 죽이면 같이 정리되므로 안내 목록에서 뺀다.
        # (E2E standalone 서버는 .next-e2e/standalone/server.js 라 여기 걸리지 않는다.)
        if "/.next/dev/" in norm:
            continue
        found.append((int(row.get("ProcessId") or 0), cmdline))
    return found


def owned_dist(cmdline: str) -> str:
    return E2E_DIST if ".next-e2e" in cmdline.replace("\\", "/").lower() else DEV_DIST


def emit_ask(reason: str) -> None:
    """차단이 아니라 '승인 요구'로 내보낸다.

    2026-09-08 사고는 승인 절차가 없어서가 아니라, 승인하는 쪽이 그 시점에 dev 서버가
    살아 있다는 사실을 몰라서 났다. 그래서 필요한 것은 금지가 아니라 정보다. deny 로
    두면 삭제 의도가 아닌 문장(테스트 문자열·사고 경위를 적은 커밋 메시지)까지 막혀
    실제로 정상 작업이 두 번 중단됐다. ask 는 점유 PID 와 종료 명령을 보여준 뒤
    사람이 판단하게 하므로, 오탐이어도 승인 한 번으로 진행된다.
    """
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }))  # ensure_ascii=True(기본) 유지: Windows 콘솔 코드페이지(cp949)로 인코딩돼
    # 훅 stdout 이 깨지는 것을 막는다. 한글은 \uXXXX 로 이스케이프되어 나간다.
    sys.exit(0)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    command = (data.get("tool_input") or {}).get("command") or ""
    if not command:
        sys.exit(0)

    targets = targeted_dists(command)
    if not targets:
        sys.exit(0)

    blockers = [(pid, cmd) for pid, cmd in next_servers() if owned_dist(cmd) in targets]
    if not blockers:
        sys.exit(0)

    pids = " ".join(str(pid) for pid in sorted(p for p, _ in blockers))
    detail = "\n".join(f"  PID {pid} ({owned_dist(cmd)} 점유): {cmd[:160]}" for pid, cmd in blockers)
    emit_ask(
        "살아있는 Next 서버 밑의 dist 삭제입니다 (guard_next_dist). 승인 여부를 확인하세요.\n"
        f"삭제 대상: {', '.join(sorted(targets))}\n{detail}\n"
        "서버를 살려둔 채 dist 를 지우면 Turbopack 색인(.meta)이 사라진 .sst 를 계속 참조해 "
        "'Unable to open static sorted file ... (os error 3)' 로 앱 전체가 깨진다(2026-09-08 사고). "
        "지우려면 서버를 먼저 종료하라:\n"
        f"  taskkill /F /T /PID {pids}\n"
        "이 서버가 다른 세션 것일 수 있으니 종료 전에 사용자에게 확인할 것. "
        "하네스(verify_harness.py)는 .next 를 건드리지 않으므로 하네스 전 청소는 대개 불필요하다.\n"
        "삭제 의도가 없는 명령(문장 안에 명령어와 dist 이름이 함께 등장한 경우)이면 그대로 승인해도 된다."
    )


if __name__ == "__main__":
    main()
