# 전략 카탈로그 화면화 & 구독 게이팅 설계안 (Strategy Catalog → Screen → Subscription)

> 상태: **설계 초안(분석 전용, 코드 미변경)** · 작성: 2026-07-18 · 소유 주제: 전략을 "화면 노출 가능한 1급 자원"으로 승격하고, 향후 구독 티어 게이팅으로 확장하는 방법
> 상위 규칙 충돌 시 `AGENTS.md` 우선. 전략 명세 정본은 `docs/strategy_specification.md`, 구현 맵은 `docs/strategy_map.md`.

---

## 0. 한 줄 결론

`strategies` 카탈로그 테이블이 **이미 존재**하므로, 스키마 대격변 없이 **컬럼 몇 개 + 유저 화면 1개 + 서버측 게이팅 1곳**만 추가하면 1:1 매핑을 그대로 두고도 구독 티어까지 확장된다. 단 착수 전 **카탈로그↔팩토리 정합성**과 **알파 마케팅 함정**을 반드시 해소해야 한다.

---

## 1. 현재 구조 (실측 기준, 추측 아님)

### 1.1 데이터/라우팅

| 요소 | 위치 | 현황 |
| :--- | :--- | :--- |
| 카탈로그 테이블 | `strategies` ([models.py:30](../../backend/app/core/models.py)) | `strategy_type`(PK) · `name_ko` · `name_en` · `description` · `is_active` — **화면·과금 메타 없음** |
| 유저↔전략 매핑 | `user_settings.strategy_type` ([models.py:112](../../backend/app/core/models.py)) | **문자열 단일 컬럼(1:1)** |
| 전략 인스턴스 생성 | `strategy_factory.get_strategy()` ([strategy_factory.py:5](../../backend/app/strategies/strategy_factory.py)) | 80여 개 하드코딩 `if/elif` 체인 |
| **2차 디스패처** | `MultiStrategyManager` ([multi_strategy_manager.py:55](../../backend/app/bot/multi_strategy_manager.py)) | `multi_slot`·`three_slot` 등 슬롯형은 팩토리가 아니라 여기서 라우팅 |
| 카탈로그 시드 | `alembic .../c8e9f0123456_seed_complete_strategy_catalog.py` 외 3개 seed | 마이그레이션으로 `strategies` 로우 삽입 |
| 읽기(노출) | `admin/router.py:234` | `is_active == True` 로우만 `available_strategies`로 반환 |
| 쓰기(검증) | `admin/router.py:409-436` | 카탈로그 **존재 여부**만 확인. 포지션/미체결 있으면 변경 차단(409) |
| 화면 | `frontend/app/admin/settings/page.tsx:547` | **관리자 설정 페이지의 드롭다운뿐**. 일반 유저용 전략 화면 없음 |
| 풍부한 메타(등급/장세/설명) | `docs/strategy_map.md` | 🥇🥈🥉🧪 · 🔥🛡️⚡📡 다 있으나 **마크다운 문서일 뿐 DB/쿼리 대상 아님** |

### 1.2 정합성 진단 실측 결과 (선행 검증 — **실제 DB 기준**)

> ⚠️ 방법론 주의: 코드를 **시드 마이그레이션 파일**과 비교하면 어긋난 것처럼 보이나(파일은 DB보다 뒤처짐), **진짜 정본은 실행 중 DB의 `strategies` 테이블**이다. 아래는 `backend/stockauto.db` 실측 결과.

인식 가능 집합 = **`strategy_factory`(107키) ∪ 멀티슬롯 매니저 특수키 4개**(`multi_slot`·`core_satellite`·`three_slot`·`multi_slot_3`) = **110**. (매니저의 `else` 분기는 단일 전략을 팩토리로 재위임하므로 별도 키가 아님.) vs 실제 DB **97행(전부 active)**.

- **팬텀(DB엔 있으나 코드가 모름 → 기본전략 폴백): 0건.** 카탈로그의 97종은 전부 코드로 동작한다. 시스템은 건강함.
- **코드로 동작하나 DB에 없음: 13건.** 그러나 내역을 뜯으면:
  - **별칭 10건(무해)**: `complex`(=strategy_c) · `xsec_momentum`(=cross_sectional_momentum) · `stockauto_v1`(=strategy_a) · `double_bb`(=double_bb_reversion) · `supernova_squeeze`(=asqs) · `complex_ep` · `complex_aggressive` · `strategy_c_ep` · `strategy_c_aggressive` · `leveraged_regime_tqqq`(=leveraged_regime_3x). 정식 키는 이미 카탈로그에 있으므로 문제 아님. 화면엔 중복 표시 안 되게 처리하는 편이 낫다.
  - **진짜 누락 3건**: `multi_slot` · `multi_slot_3` · `three_slot`. 실제 운용되는 격리형 슬롯 모드로 seed 파일엔 있으나 이 DB엔 미삽입. admin6/admin7 계정이 이 값으로 도는데(`migrator.py:112`) 카탈로그엔 없어 화면 선택 불가.

> **정본 결론: DB↔코드 불일치는 실질적으로 "슬롯 모드 3종의 카탈로그 미등록" 하나뿐이며, 나머지는 별칭 중복 정리(미관) 사안이다.** 앞선 "18종 누락" 진단은 DB가 아니라 시드 파일과 비교한 오판이었다.

---

## 2. 목표 / 비목표

**목표**
1. 전략을 유저가 화면에서 **보고 이해하고 선택**할 수 있는 1급 자원으로 승격.
2. 향후 구독 티어(예: free / pro)로 **선택 가능한 전략 집합을 게이팅**할 수 있는 데이터 골격 확보.
3. 1:1 매핑(`user_settings.strategy_type`) **유지** — 이번 범위에서 다중 전략/포트폴리오로 바꾸지 않음.

**비목표 (이번 설계 범위 밖)**
- 전략 성능 랭킹/추천 알고리즘.
- 다중 전략 동시 실행(1:N).

> **⚠️ 범위 확정 (2026-07-18, 사용자 결정): "전략 카탈로그 화면"만 진행. 구독·과금 전체 보류.**
> 현실성 진단(§7) 결과 — 화면화는 저위험이나 구독 과금은 규제(투자일임/로보어드바이저 인가 가능성)·가치명분(QQQ 초과 알파 없음)·계정 성숙도(이메일 없는 가입)의 벽이 코드 밖에 있음. 따라서 **화면화(S0~S3)와 구독(S4)을 분리**하고 구독은 그 벽들이 해소될 때까지 미룬다.
> - **이번 범위 IN**: S0(정합성 정리+가드) · S1(화면 메타 컬럼, 단 `min_plan` 제외) · S2(쓰기검증 필터) · S3(유저 카탈로그 화면).
> - **보류 OUT**: `min_plan`·`users.plan`·`subscriptions`·티어 게이팅·그랜드파더링·결제(S4). 나중에 붙일 때 `min_plan` 컬럼 1개 추가로 확장 가능하도록 다른 메타 컬럼은 이번에 살려둔다.

---

## 3. 제안 설계 (3레이어)

### 레이어 1 — 카탈로그 테이블에 "화면·과금 메타" 추가

`strategies` 테이블에 컬럼 추가(모두 nullable + 기본값으로 무중단 마이그레이션):

| 컬럼 | 타입 | 용도 | 기본값 |
| :--- | :--- | :--- | :--- |
| `tier` | String | 등급 배지 (`gold`/`silver`/`bronze`/`sandbox`/`single`) | `'single'` |
| `regime` | String | 활성 장세 (`ALL`/`BULLISH`/`BEARISH`/`NEUTRAL`) | `'ALL'` |
| `summary_ko` | Text | 카드용 한 줄 요약 | `NULL` |
| `min_plan` | String | 접근 최소 플랜 (`free`/`pro`/...) | `'free'` |
| `sort_order` | Integer | 화면 정렬 우선순위 | `0` |
| `is_selectable` | Boolean | 유저가 직접 고를 수 있는지(연구/내부 전용 숨김용) | `true` |

- 값의 정본은 `docs/strategy_map.md` — 시드 마이그레이션이 그 내용을 DB로 승격.
- `min_plan`·`is_selectable`가 **구독 게이팅의 데이터 축**. 스키마 대격변 없이 컬럼 추가만으로 확장.

> SSOT 주의: 등급/장세/요약의 **정본은 카탈로그 테이블**로 단일화하고, `strategy_map.md`는 사람이 읽는 참조로 둔다. 두 곳을 동시에 "정본"으로 두면 드리프트가 재발한다.

### 레이어 2 — 유저용 전략 카탈로그 화면

- 관리자 전용 드롭다운을, 일반 유저에게는 **배지 카드 그리드**로 노출(등급·장세 이모지 + `summary_ko`).
- 데이터 소스: `is_active AND is_selectable` 로우. `min_plan > 유저 플랜`인 카드는 **잠금(🔒) 표시 + 업셀**, 선택 불가.
- 선택 시 기존 저장 API 재사용. **포지션/미체결 있으면 변경 차단(409)** 규칙은 그대로 유지([router.py:430](../../backend/app/admin/router.py)).
- 신규 유저용 읽기 엔드포인트: `GET /strategies/catalog` (플랜 반영된 목록 + 잠금 상태). `API_STANDARD.md`의 전역 응답 래퍼 준수.

### 레이어 3 — 구독 게이팅 (서버측 강제)

- 유저 플랜 저장 위치(택1, 후속 결정 사항): `users.plan` 컬럼 추가 or 별도 `subscriptions` 테이블. 결제 연동 계획에 따라 결정.
- **강제 지점은 쓰기 경로**: `admin/router.py`의 전략 저장 검증([router.py:409-436](../../backend/app/admin/router.py))에 다음을 추가:
  1. `is_active == True` **AND** `is_selectable == True` 필터 (현재는 존재 여부만 봄 → 비활성/내부 전략도 통과하는 구멍).
  2. `strategy.min_plan` ≤ `user.plan` 엔타이틀먼트 검사. 미달 시 403.
- 프론트의 잠금 표시는 UX일 뿐. **직접 POST 우회 방어는 반드시 서버에서.**

---

## 4. 반드시 짚을 함정 (Zero-Complacency)

1. **알파 마케팅 함정 — 최우선.** 검증 기록상 *능동 타이밍으로 QQQ 초과 알파는 없음*(챔피언십 재확인, 비교군 전부 음의 알파). 구독 카피가 "이 전략 쓰면 시장을 이긴다"를 **암시하면 사실과 어긋나고 분쟁 소지**. 화면 문구는 "성향/스타일별 선택"으로 한정하고, **수익률 우위·수익 보장 표현 금지**. 또한 개인화된 투자자문으로 읽히지 않게(면책 문구 필요). → 이는 제품/법무 정책 사항이지 개발 편의로 넘길 수 없음.
2. **정합성 검사는 반드시 "실제 DB" 기준으로.** 코드를 시드 *파일*과 비교하면 허위 드리프트가 잡힌다(파일 < DB). 실측 정본으로는 팬텀 0·진짜 누락은 슬롯 3종뿐(§1.2). 또한 인식 집합은 **팩토리 ∪ 멀티슬롯 매니저**이므로, 팩토리만 비교하면 슬롯형을 오탐한다. → 이 대조(실DB vs 팩토리∪매니저)를 `verify_harness`에 상시 가드로 넣어 재발을 자동 차단해야 함.
3. **쓰기 검증의 `is_active` 미필터 구멍.** 현재 저장 검증은 존재 여부만 확인([router.py:413](../../backend/app/admin/router.py)) → 비활성/프리미엄 전략도 직접 POST로 저장 가능. 게이팅의 실효성은 이 지점 수정에 달려 있음.
4. **별칭(alias) 처리.** `strategy_c`↔`complex`, `xsec_momentum`↔`cross_sectional_momentum` 등 다대일 별칭이 카탈로그에 중복 로우로 존재. 화면에 별칭이 중복 카드로 뜨지 않게 `is_selectable`/canonical 지정 필요.
5. **기존 유저 마이그레이션 안전성.** 이미 프리미엄 전략을 쓰던 유저가 게이팅 도입으로 갑자기 차단되면 봇이 멈출 수 있음. 신규 컬럼은 기본 `free`/`is_selectable=true`로 시작하고, 게이팅은 **그랜드파더링(기존 선택 유지)** 정책을 명시한 뒤 별도 단계에서 활성화.

---

## 5. 단계별 실행 로드맵 (승인 후, 각 단계 독립 검증)

| 단계 | 내용 | 산출물 | 코드 변경 |
| :--- | :--- | :--- | :--- |
| S0 | **정합성 정리 + 가드**: 슬롯 3종(`multi_slot`/`multi_slot_3`/`three_slot`) 카탈로그 등록 or 내부전용 제외 결정, 별칭 10종 canonical 지정(화면 중복 방지), **실DB↔코드 대조를 `verify_harness`에 상시 가드로 추가** | seed 마이그레이션, verify_harness | 소~중 |
| S1 | 카탈로그 컬럼 추가(레이어 1) + `strategy_map.md` 값 시드 | alembic 마이그레이션, 모델 | 중 |
| S2 | 쓰기 검증에 `is_active/is_selectable` 필터 추가(구멍 3 봉합) | `admin/router.py` | 소 |
| S3 | 유저 카탈로그 읽기 API + 화면(레이어 2) | 라우터, React | 중 |
| S4 | 플랜 저장소 + 엔타이틀먼트 게이팅(레이어 3) + 그랜드파더링 | 모델, 라우터, 프론트 | 대 |

> 각 단계 완료 보고 전 `python scripts/verify_harness.py` 통과 필수. S1·S4는 `SCHEMA.md` 갱신 동반.

---

## 6. 결정 사항

**확정 (2026-07-18, 사용자 결정)**
- 슬롯 3종(`multi_slot`·`multi_slot_3`·`three_slot`) → **카탈로그에 노출**. 유저가 고를 수 있는 정식 전략으로 등록(S0에서 시드). 별칭 10종은 canonical로 접어 화면 중복 방지.
- 실DB↔코드 대조를 `verify_harness` 상시 가드로 편입하는 방향 합의. 단 **구현은 보류**(설계 단계에서 멈춤) — 별도 세션에서 S0부터 착수.
- **플랜 저장 = 2단계 순차.** ①지금: `users.plan` 단일 컬럼을 게이팅 read-model로 도입(현재 유효 티어 하나만 보관). ②결제 연동 시: `subscriptions` 테이블(상태/만료일/PG거래ID/이력)을 정본으로 신설하고, `users.plan`은 그 구독의 현재 상태를 비추는 **캐시(projection)로 강등**. → 정규화 이력 + 비정규화 현재티어의 표준 패턴. 빈 껍데기 스키마 선제작 회피.
- **초기 티어 = "선택폭·기능"으로 분리(수익 아님).** free=실사용 가능한 안전 기본 1~2종(예: `regime_switching`+`senior_simple`), pro=단일전략 전체 + 슬롯 모드 + 백테스트 아레나. 메달 등급(🥇🥈🥉)은 **내부 분류로만** 쓰고 가격표엔 붙이지 않음(‘돈=수익’ 암시 = 알파 함정, §4-1).
- **그랜드파더링 = 기존 선택 유지.** 게이팅 시행 시 유저가 이미 `user_settings.strategy_type`에 담은 값은 플랜 초과라도 유효. 실제 *상위 전략으로 변경할 때만* `min_plan` 검사(`new == current` 무변경은 항상 통과). 기존 "포지션 보유 중 변경 불가" 규칙과 맞물려 봇 중단 위험 없음.

> 위 플랜/티어/그랜드파더링 결정은 **구독을 실제로 붙일 때(S4)** 적용할 사전 합의이며, 이번 범위에서는 구현하지 않는다(§2 범위 확정).

**미정 (구독 착수 시 확인)**
- pro 위 상위 티어(엔터프라이즈 등) 추가 여부 및 각 티어 실제 가격.
- 결제 PG사 선정 및 `subscriptions` 스키마 상세(청구주기/환불/무료체험).

---

## 7. 현실성(Feasibility) 진단 — 실코드 기반 (2026-07-18)

### 🟢 기술 기반은 성숙 (화면화 저위험)
실측으로 구독/멀티유저의 전제조건이 이미 존재:
- **멀티테넌트 자동매매 엔진**: `is_running` 유저 전체를 순회하며 유저별 브로커로 주문 처리([scheduler.py:1932](../../backend/app/bot/scheduler.py), "Multi-tenant 3-Mode Unified Engine").
- **셀프 회원가입 + JWT + 역할(USER/ADMIN)**([auth/router.py:213](../../backend/app/auth/router.py)).
- **3-모드(SIMULATED/MOCK/REAL) + 유저별 인증정보 격리**, 카탈로그 97종 정상 동작.
→ 카탈로그 화면·게이팅 데이터 모델의 90%가 이미 있어 **S0~S3는 저위험·소규모**.

### 🔴 구독 과금은 코드 밖의 벽 (그래서 분리·보류)
(아래 규제 항목은 법률 전문가 확인이 필요한 **가설**이며 확정된 법 해석이 아님.)
1. **규제 — 최대 관문.** REAL 모드로 타인의 실계좌에 자동매매를 집행하고 구독료를 받는 것은 한국에서 **투자일임업/로보어드바이저(자본시장법, 금융위 인가)** 영역일 가능성이 큼. 무인가 영업 리스크.
2. **가치 명분.** 능동 타이밍 QQQ 초과 알파 없음(검증 기록). 수익 우위를 팔 수 없으므로 정직한 명분은 자동화·편의·교육뿐 → WTP 낮음.
3. **스퀴즈 딜레마.** REAL=규제·책임 / SIMULATED=규제 경량이나 "알파 없는 모의투자" 구독 WTP 취약. 양쪽 다 좁음.
4. **계정 성숙도 갭.** 가입이 아이디+비번뿐, **이메일 없음** → 유료 서비스 필수인 계정 복구·결제 신원·영수증 기반 부재.

### 권고
**"전략 카탈로그 화면(S0~S3)"과 "구독 과금(S4)"을 분리.** 화면화는 알파와 무관하게 UX 가치가 실재하므로 지금 진행 가능(무료로 풀어도 이득). 구독은 위 4개 벽(특히 1·2)이 해소되기 전까지 `min_plan` 등 과금 데이터/청구 파이프라인을 붙이지 않는다.

---

## 참고 (Cross-refs)

- 전략 명세 정본: [strategy_specification.md](../strategy_specification.md)
- 전략↔소스 구현 맵: [strategy_map.md](../strategy_map.md)
- DB 스키마 정본: [SCHEMA.md](../SCHEMA.md)
- API 응답 계약: [API_STANDARD.md](../API_STANDARD.md)
