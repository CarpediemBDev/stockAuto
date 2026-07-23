# 🔀 다중 세션 작업 격리 규칙 (Multi-Session Worktree Isolation)

> **적용 대상: 이 저장소에서 파일을 수정하는 모든 주체** — Claude 세션, Antigravity, 다른 AI 에이전트, 사람(IDE/터미널).
> 상위 규칙은 [`AGENTS.md`](../AGENTS.md) §9이며, 이 문서는 그 실행 세부를 담는다.

## 1. 왜 필요한가 (실제 사고 기록)

문제의 원인은 **"AI끼리 충돌"이 아니라 하나의 작업 디렉터리(워킹트리)와 하나의 git HEAD/인덱스를 여러 주체가 동시에 쓰는 것**이다. 주체가 무엇이든 동일하게 터진다.

2026-07-18~19 세션에서 실제로 발생한 사고:

| 사고 | 원인 |
| :--- | :--- |
| A 세션의 미커밋 파일이 B 세션 커밋에 통째로 섞여 들어감 | 워킹트리 공유 |
| 커밋하려는 순간 `detached HEAD` 상태로 전환됨 | 다른 세션이 브랜치 변경 |
| 작업 중이던 브랜치가 예고 없이 `main`으로 바뀜 | 같은 체크아웃 |
| `scheduler.py`에 본인이 하지 않은 수정이 떠 있음 | 동시 편집 |
| 커밋 시 남의 미커밋 파일이 스테이징에 섞일 위험 | 공유 인덱스 |

**중요**: 이 문제는 파일을 잘게 쪼개도 해결되지 않는다. 리팩터링이 아니라 **작업 디렉터리 분리**로만 해결된다.

## 2. 핵심 규칙

> **worktree는 "AI 종류"당 1개가 아니라, "동시에 파일을 수정하는 세션"당 1개다.**

*   **쓰기 세션(파일 편집·커밋·브랜치 전환)** → 반드시 **자기 전용 worktree**에서만 작업한다.
*   **읽기 전용 세션(코드 분석·리뷰·질의응답·계획 수립)** → worktree 불필요. 어느 폴더에서든 읽어도 충돌하지 않는다.
*   각 세션은 **자기 폴더 밖의 파일을 절대 수정하지 않는다.** 다른 worktree의 미커밋 변경을 커밋하거나 stash하지 않는다.

## 3. 현재 폴더 배치 (쓰기 세션 2개 기준)

| 경로 | 용도 | 비고 |
| :--- | :--- | :--- |
| `D:\dev\workspace\stockAuto\` | 쓰기 세션 #1 (메인 체크아웃) | 기본 포트 8000/3000 |
| `D:\dev\workspace\stockAuto-ag\` | 쓰기 세션 #2 (Antigravity 등) | 브랜치 `ag/base`에서 시작 |

*   폴더는 오래 유지하고, **브랜치는 그 안에서 작업마다 새로 딴다.** 폴더↔세션 매핑만 고정한다.
*   git 제약상 **같은 브랜치를 두 worktree가 동시에 체크아웃할 수 없다.** (`main`은 메인 체크아웃이 점유)
*   커밋·브랜치는 하나의 저장소를 공유하므로 서로의 커밋이 정상적으로 보이고 머지도 평소와 같다.

## 4. worktree 만들기 / 쓰기

```bash
# 생성 (origin/main 기준 새 브랜치)
git worktree add ../stockAuto-ag -b ag/base origin/main

# 목록 확인
git worktree list

# 제거
git worktree remove ../stockAuto-ag
```

폴더 안에서는 평소처럼 브랜치를 딴다:

```bash
cd ../stockAuto-ag
git checkout -b feat/새작업 origin/main
```

## 5. 신규 worktree 세팅 체크리스트 (gitignore라 복사되지 않음)

worktree는 **소스만** 체크아웃된다. 아래는 폴더마다 별도로 준비해야 한다.

| 항목 | 조치 |
| :--- | :--- |
| `backend/venv/` | `python -m venv venv` 후 `pip install -r requirements.txt -r requirements-dev.txt` |
| `frontend/node_modules/` | `npm install` |
| `backend/app/scanner/node_modules/` | `npm install` (Puppeteer 스크래퍼용) |
| `backend/.env.local` (+ `.env.dev`/`.env.prod`) | 메인에서 복사 |
| `frontend/.env.local` (+ `.env.dev`/`.env.prod`) | 메인에서 복사 |
| `backend/stockauto.db` | 메인에서 복사 또는 새로 시딩 |
| `.claude/launch.json`, `.claude/settings*.json` | 메인에서 복사 (없으면 preview 기동 불가) |

> 의존성은 **worktree마다 각자 설치**를 원칙으로 한다. 정크션(`mklink /J`)으로 공유하면 디스크·시간은 절약되지만, 한 세션의 `npm install`/`pip install`이 다른 세션에 즉시 영향을 주므로 브랜치별 의존성이 다를 때 위험하다.

## 6. 공유 자원 주의 (worktree로도 분리되지 않는 것)

worktree는 **파일과 브랜치**를 분리할 뿐, 아래 자원은 여전히 공유된다.

*   **포트**: 백엔드 `8000`은 `backend/run.py`에 하드코딩되어 env로 바꿀 수 없다. 프론트는 `launch.json`의 `autoPort: true`로 자동 회피된다.
    → **앱(백엔드) 구동은 한 번에 한 worktree만.**
*   **`python scripts/verify_harness.py` 동시 실행 금지.** 포트(3000/3100)·DB 경합으로 서로의 E2E를 깨뜨린다. 반드시 **순차 실행**한다.
*   **Redis/Memurai(6379) 공유**: 주문 락(`acquire_symbol_order_lock` 등)을 공유하므로 두 세션이 동시에 매매 봇을 돌리면 락이 간섭한다. **봇 동시 구동 금지**(또는 Redis DB 인덱스 분리).
*   **DB 파일은 폴더별로 분리**되므로 데이터가 서로 다르게 흘러간다. 실DB를 읽는 검사(`scripts/check_strategy_consistency.py` 등)의 결과가 폴더마다 다를 수 있음을 감안한다.

## 7. 세션 시작 시 자가 점검 (필수)

작업(수정)을 시작하기 전에 반드시 확인한다.

```bash
git worktree list          # 내가 어느 폴더에 있는지
git branch --show-current  # 내 브랜치가 맞는지
git status --short         # 내가 만들지 않은 미커밋 변경이 있는지
```

*   **내가 만들지 않은 미커밋 변경이 보이면 다른 세션의 작업이다.** 절대 `git add -A`/`git commit -a`로 쓸어 담지 말고, **자기 파일만 명시적으로 스테이징**한다.
*   브랜치가 예상과 다르면 즉시 멈추고 상황을 보고한다. 임의로 `checkout`/`reset --hard`로 남의 작업을 지우지 않는다.

## 8. 향후 개선 후보

*   `backend/run.py:78`의 `port = 8000` 하드코딩을 `int(os.environ.get("PORT", 8000))`으로 바꾸면 worktree별 백엔드 포트 분리가 가능해져 "앱 동시 구동 금지" 제약이 사라진다.
