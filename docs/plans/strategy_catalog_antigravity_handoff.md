# 전략 카탈로그 화면화 — Antigravity 개발 인수인계 브리프

> 대상: **Antigravity(개발 에이전트)**. 검증: **Claude(verify_harness 실행)** — 우리 협업 틀(개발↔검증 분리).
> 설계 정본: [strategy_catalog_screen_and_subscription.md](strategy_catalog_screen_and_subscription.md). 본 문서는 그 설계의 **실행 지시서**다.
> **범위: 전략 카탈로그 화면(S0~S3)만. 구독·과금(S4)·`min_plan`·`users.plan`·`subscriptions`는 절대 손대지 말 것.**

## 0. 불변 수칙 (프로젝트 규칙)
- Git `add/commit/push` 자율 실행 금지 — 사용자가 명시할 때만.
- 코딩 시작 전 `docs/tasks/YYYY-MM-DD.md`에 `[ ]`→`[/]` 선등록.
- 완료 보고 전 `python scripts/verify_harness.py` 통과. 못 하면 "미검증"으로 사유 보고.
- 백엔드 pytest/스크립트는 `backend/venv/Scripts/python.exe`로 실행(시스템 python엔 alembic 미설치).
- 한글 문서·주석·커밋은 NFC 완성형.

## 1. 배경 사실 (실측, 재확인 불필요)
- **라우팅 디스패처 2개**: ① `strategy_factory.get_strategy()`([strategy_factory.py](../../backend/app/strategies/strategy_factory.py)) ② `MultiStrategyManager`([multi_strategy_manager.py:55](../../backend/app/bot/multi_strategy_manager.py), 특수키 `multi_slot`·`core_satellite`·`three_slot`·`multi_slot_3`, else는 팩토리로 재위임).
- **인식 가능 집합** = 팩토리 107키 ∪ 멀티슬롯 특수키 4 = **110**. 실제 DB `strategies` = **97행(전부 active)**.
- **팬텀 0**(DB 전 항목이 동작함). **진짜 누락 = 슬롯 3종**(`multi_slot`/`multi_slot_3`/`three_slot`) — DB 미등록인데 admin6/7이 사용(`migrator.py:112`).
- **별칭 10종**(DB에 canonical만 있고 별칭 키는 없음): `complex`(=strategy_c)·`complex_aggressive`·`complex_ep`·`double_bb`(=double_bb_reversion)·`leveraged_regime_tqqq`(=leveraged_regime_3x)·`stockauto_v1`(=strategy_a)·`strategy_c_aggressive`·`strategy_c_ep`·`supernova_squeeze`(=asqs)·`xsec_momentum`(=cross_sectional_momentum). **→ 별칭은 DB 로우로 추가하지 말 것(중복 카드 방지).**
- 읽기 경로: `admin/router.py:234` — `is_active==True` 로우를 `available_strategies`로 반환.
- 쓰기 검증: `admin/router.py:409-436` — 현재 **존재 여부만** 확인(`is_active`/`is_selectable` 미필터, line 413).
- 관리자 화면 드롭다운: `frontend/app/admin/settings/page.tsx:547`. **유저용 전략 화면은 없음.**
- 메타데이터 값 출처: 등급(🥇🥈🥉🧪)·장세(🔥🛡️⚡📡)·요약은 [strategy_map.md](../strategy_map.md), 명칭은 seed `c8e9f0123456...`의 STRATEGIES 튜플.

---

## 2. 작업 단계 (원인 → 명령 → 기대결과)

### S0 — 정합성 정리 + 재발방지 가드
- **원인:** 슬롯 3종이 코드로 동작하나 카탈로그 미등록 → 화면에서 선택 불가. 그리고 이런 DB↔코드 드리프트를 사람이 매번 눈으로 확인해 놓쳐 옴.
- **명령:**
  1. 새 alembic 마이그레이션 추가(기존 `c8e9f0123456...` 패턴 참고: 존재 키 조회 후 없는 것만 삽입 = 멱등). `multi_slot`·`multi_slot_3`·`three_slot` 3행을 `is_active=True`로 upsert. 명칭은 STRATEGIES 튜플 값 재사용. **별칭 10종은 삽입 금지.**
  2. `scripts/verify_harness.py`에 **정합성 가드** 추가: 실행 중 DB의 `strategies` 전 로우가 (팩토리 ∪ 멀티슬롯 특수키) 안에 있는지 검사. **팬텀(DB엔 있으나 코드가 모름) 1건이라도 있으면 FAIL.** 반대 방향(코드엔 있으나 DB엔 없음=별칭 등)은 **WARN만**(FAIL 아님 — 의도된 별칭 존재). 디스패처 2개를 모두 인식 집합에 반영할 것(팩토리만 보면 슬롯 오탐).
- **기대결과:** 마이그레이션 후 DB에 슬롯 3종 노출. `verify_harness` 실행 시 팬텀 0으로 통과. 이후 누가 팩토리에만 전략을 추가하고 카탈로그를 빠뜨리면(또는 그 반대로 DB에 유령을 넣으면) 커밋이 자동 차단.

### S1 — 카탈로그 화면 메타 컬럼
- **원인:** 유저 화면에 등급·장세 배지와 한 줄 요약을 뿌리려면 DB에 메타가 있어야 함(현재 `strategies`는 이름/설명/is_active뿐).
- **명령:** `Strategy` 모델([models.py:30](../../backend/app/core/models.py))과 마이그레이션에 컬럼 추가 — **모두 nullable+기본값(무중단)**:
  - `tier` String default `'single'` (gold/silver/bronze/sandbox/single)
  - `regime` String default `'ALL'` (ALL/BULLISH/BEARISH/NEUTRAL)
  - `summary_ko` Text nullable
  - `sort_order` Integer default `0`
  - `is_selectable` Boolean default `true`
  - **`min_plan`은 추가하지 말 것(구독 범위, 보류).**
  값은 `strategy_map.md` 기준으로 시드(헤드라인 전략부터, 나머지는 기본값 허용). 슬롯형·연구용 중 유저 비노출 대상은 `is_selectable=false`.
- **기대결과:** `SCHEMA.md` 갱신. 컬럼 추가로 기존 데이터·API 무손상.

### S2 — 쓰기 검증 구멍 봉합
- **원인:** 전략 저장 검증이 존재 여부만 봐서 `is_active=false`/`is_selectable=false` 전략도 직접 POST로 저장 가능(`admin/router.py:413`).
- **명령:** 해당 쿼리에 `Strategy.is_active==True` **AND** `Strategy.is_selectable==True` 필터 추가. 미달 시 기존과 동일한 400 에러. **기존 "포지션/미체결 보유 중 변경 불가" 규칙(430행)은 유지.**
- **기대결과:** 비노출 전략은 API로도 선택 불가. 회귀 테스트(`test_api_integration.py` 등) 통과.

### S3 — 유저용 전략 카탈로그 화면 + 읽기 API
- **원인:** 전략 선택이 관리자 드롭다운에만 있음. 유저가 스스로 보고 이해·선택할 화면이 없음.
- **명령:**
  1. 읽기 엔드포인트 `GET /strategies/catalog` — `is_active AND is_selectable` 로우를 `tier`·`regime`·`summary_ko`·`sort_order` 포함해 반환. 전역 응답 래퍼([API_STANDARD.md](../API_STANDARD.md)) 준수. 별칭은 canonical만 노출.
  2. 프론트: 배지 카드 그리드 화면. 선택 시 **기존 저장 API 재사용**(신규 매핑 로직 만들지 말 것 — SSOT). 등급·장세 이모지 + 요약 표시.
  3. **문구 주의(알파 함정):** "수익 우위/시장 초과" 암시 금지. "성향/스타일별 선택"으로만. 투자자문처럼 읽히지 않게.
- **기대결과:** 유저가 카탈로그 화면에서 전략을 골라 저장. 저장·기동 흐름은 기존과 동일하게 동작(verify로 확인).

---

## 3. 절대 하지 말 것 (Out of scope)
- `min_plan`·`users.plan`·`subscriptions` 테이블·티어 게이팅·그랜드파더링·결제 — 전부 보류(S4). 근거: 설계 §7 현실성 진단(규제·알파·계정성숙 벽).
- 별칭 10종을 카탈로그 로우로 추가.
- `user_settings.strategy_type` 1:1 매핑을 다중 전략으로 바꾸기.
- 전략 매핑/선택 로직 신규 구현(기존 저장 API 재사용).

## 4. 완료 시 (Claude 검증 인계)
각 단계 후 `python scripts/verify_harness.py`(계약/컴파일/pytest/lint/tsc/카오스/롤백 + 신규 정합성 가드) 통과. 통과 결과·미해결 위험·다음 시작점을 `docs/tasks/YYYY-MM-DD.md` 인수인계에 남길 것. Claude는 지시가 있을 때 검증을 재실행한다.
