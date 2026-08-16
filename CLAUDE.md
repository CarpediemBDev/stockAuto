# CLAUDE.md — StockAuto 세션 부트스트랩 (Claude Code 진입점)

> 이 파일은 **Claude Code가 세션 시작 시 자동 로딩**하는 진입점입니다.
> 규칙의 **단일 원장(SSOT)은 [`AGENTS.md`](AGENTS.md)** 이며, 이 파일은 Claude 세션이
> 그 규칙에 곧바로 도달·집행하도록 요약·연결·번역하는 브리지입니다.
> 상세·최신 규칙이 충돌하면 항상 `AGENTS.md`가 우선합니다.

## 1. 시작하면 이 순서로 읽는다 (Cold Start)

1. **[`docs/README.md`](docs/README.md)** — 문서 지도(SSOT 인덱스). 어디에 뭐가 있는지 먼저 파악.
2. **[`AGENTS.md`](AGENTS.md)** — 프로젝트 절대 수칙 전문.
3. **최신 [`docs/tasks/`](docs/tasks)`/YYYY-MM-DD.md`** — 오늘/직전 현황판. 진행 중(`[/]`)·승인대기(`[R]`) 항목, 인수인계, 미해결 위험 확인.
4. 변경할 **실제 코드와 계약 문서**(`docs/SCHEMA.md`, `docs/API_STANDARD.md` 등)를 직접 열어 확인. 추측 금지.

> 오늘 현황판이 없으면 **`python scripts/new_task.py`**로 표준 양식(변경 영향 기록 9필드 포함)을 생성한 뒤 채운다.

## 2. 절대 어기면 안 되는 불문율 (Non-Negotiables)

- **Git 동결 & 트리거별 정지선:** `git add/commit/push/checkout` 등 상태 변경 명령 **자율 실행 금지**. 트리거마다 도달 지점이 다르다 — "로컬 커밋만"(커밋까지) / "커밋하자·올리자"(**PR 상정까지, 병합 안 함**) / "머지까지 진행해"(병합·정리까지). 단독 "진행해"로 병합·브랜치 삭제 금지. 푸시·병합 직전 보고 의무. 조회용 `git status`, `git log`만 허용.
- **분석 전용 = 코드 수정 금지:** 사용자가 질문·검토만 요청하면 코드를 고치지 않고 분석·계획만 제시한다.
- **작업 선등록:** 코딩 시작 전 당일 `docs/tasks/YYYY-MM-DD.md`에 `[ ]`→`[/]`로 등록한다. 선등록 없는 코딩 금지.
- **완료 보고 전 검증:** 보고 전 **`python scripts/verify_harness.py`**를 통과시킨다(계약/컴파일/pytest/lint/tsc/카오스/롤백). 통과 못 하면 "미검증"으로 사유와 함께 보고.
- **상태 승격 규칙:** 구현·검증 끝 = `[R]`(승인대기). 사용자가 명시적으로 "승인"해야 `[x]`.
- **한글 + NFC:** 커밋 메시지·문서·주석의 한글은 **완성형(NFC)**으로 저장. 커밋 메시지는 구체적 한글.
- **계약 기록 형식:** `### 변경 영향 기록`의 9필드는 반드시 `- 필드: 내용`(하이픈, 별표/볼드 금지). 틀리면 하네스가 반려.
- **SSOT 우선:** 새 로직 작성 전 `rg`로 동일·유사 기능(손익·수수료·수량 계산, API, 캐시, 스케줄러)을 전수 검색해 중복 구현을 막는다.
- **Zero-Complacency 감사관:** 코드 검토 시 "괜찮다" 식 통과 금지. 엣지 케이스·소수점/금융 오차·레이스 컨디션을 최소 3개 비판적으로 찾는다.

## 3. 런타임 도구 번역표 (Codex/Antigravity → Claude Code)

`AGENTS.md §9`, `docs/AI_WORKFLOW.md §6`, `skills/multi-agent-collaboration/SKILL.md`는
Antigravity/Codex 도구 이름으로 쓰여 있다. **Claude 세션은 아래로 치환해 실행한다:**

| 문서상 표기 (Codex) | Claude Code 실제 도구 |
| :--- | :--- |
| `view_file`, `list_dir` | `Read`, `Glob` |
| `grep_search` | `Grep` |
| `run_command` | `Bash` (또는 `PowerShell`) |
| `define_subagent` + `invoke_subagent` | `Task` 도구 (`subagent_type` 지정) |
| `enable_write_tools: false` | 읽기 전용 서브에이전트(예: `Explore`) 선택 |
| 3대 협업 역할(Researcher/Critical Auditor/QA) | `Task`로 역할별 프롬프트 위임, 또는 메인 세션이 순차 수행 |
| 커밋 서명 `Co-authored-by: Antigravity <noreply@google.com>` | `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` |

> 커밋 서명은 **그 커밋을 실제로 만든 세션**을 기록하는 값이다(`AGENTS.md §2`). Claude 세션이 안티그래비티 서명을 대신 붙이거나 그 반대로 하지 않는다. 다른 세션이 워킹트리에 남긴 변경을 함께 커밋하면 서명이 사실과 달라지므로, 커밋 전 `git status`로 내 슬라이스만 스테이징한다.

> 즉 멀티 에이전트 파이프라인의 **의도(분석→비판감사→하네스 검증)는 그대로 따르되**, 호출은 Claude의 `Task` 도구로 한다. `.codex/skills` 개인 설치본은 참조하지 않고 이 저장소의 `skills/`를 기준으로 한다.

## 4. 세션 연속성 (여러 세션이 같은 상태를 공유)

- **모든 작업 상태의 SSOT는 `docs/tasks/YYYY-MM-DD.md`**다. 다른 세션이 무엇을 했는지는 여기(+인수인계 섹션)와 `git status`로 파악한다. 세션 메모리에 의존하지 않는다.
- 작업 종료 시 현황판 인수인계에 **마지막 검증 결과·미해결 위험·다음 시작 지점**을 남긴다. 다음 세션은 그걸 읽고 이어간다.
- 규칙 상세는 언제나 `AGENTS.md` → `docs/AI_WORKFLOW.md` → `skills/` 순으로 확인한다.

## 5. 자주 쓰는 명령

```bash
python scripts/new_task.py            # 오늘 현황판 표준 양식 생성
python scripts/verify_harness.py      # 완료 보고 전 필수 통과 검증
cd backend && python run.py local     # 백엔드(로컬 SIMULATED) 기동
cd frontend && npm run local          # 프론트 로컬 기동
```
