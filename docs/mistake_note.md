# 🚨 StockAuto 오답노트 (개발 에러 및 해결 내역)

이 문서는 프로젝트 운영 중 발생한 치명적인 버그나 시스템 장애의 근본 원인(Root Cause)과 해결 과정(Resolution)을 기록하여, 추후 동일한 문제의 재발을 방지하고 시스템의 안정성을 높이기 위해 관리됩니다.

---

## [Bug-001] "보유 종목 트레일링 스탑/손절매 미작동 (무한 홀딩) 이슈"

### 📅 발생 일시
- **발견일**: 2026-05-30
- **영향 범위**: 백엔드 스캐너 및 스케줄러 (`scanner.py`, `scheduler.py`)

### 🔍 현상 (Symptom)
- 사용자가 설정한 동적 트레일링 스탑(예: 최고가 대비 -15% 이탈) 조건이 명백히 충족되었음에도 불구하고, 봇이 매도 주문을 실행하지 않고 해당 종목을 계속해서 무한 홀딩함.
- 프론트엔드 대시보드에는 하락 수치가 표시되나, 봇 내부에서는 아무런 액션을 취하지 않음.

### 🕵️ 근본 원인 (Root Cause)
- 백엔드 스케줄러가 매도 조건을 검사하기 위해 개별 종목 분석 함수 `analyze_single_ticker()`를 호출함.
- 이 함수 내부에서 단기 이동평균선(EMA9, EMA20)을 계산할 때, 종가(Close) 단일 컬럼(`Series`) 데이터만 넘겨야 하나, 실수로 시/고/저/종가 전체가 포함된 데이터프레임(`DataFrame`) 자체를 통째로 전달함.
- `calculate_ema(df_15m, 9)`가 데이터프레임을 반환하게 되고, 후속 논리 연산에서 `ValueError: The truth value of a Series is ambiguous` 에러가 발생하며 크래시 됨.
- 분석 함수가 크래시 되면서 `None`을 반환하게 되어, 스케줄러는 해당 종목 분석을 '실패'로 간주하고 다음 사이클로 스킵해버림. (즉, 매도 조건 검사 로직 자체가 영원히 실행되지 않음)

### 🛠️ 해결 조치 (Resolution)
- **수정 파일**: `backend/app/scanner/scanner.py`
- **수정 내용**: 이동평균선 함수 호출 시 `['Close']` 컬럼을 명시하여 정확한 데이터 타입(Series)을 전달하도록 수정.
```python
# 수정 전
ema9 = calculate_ema(df_15m, 9)
ema20 = calculate_ema(df_15m, 20)

# 수정 후
ema9 = calculate_ema(df_15m['Close'], 9)
ema20 = calculate_ema(df_15m['Close'], 20)
```
- **검증**: 독립된 테스트 스크립트를 통해 에러 없이 `signal_score`가 정상 반환됨을 확인 완료. 이후 봇은 정상적으로 손절 및 익절 로직을 수행함.

---

## [Bug-002] "MarketHeader 시장 개요 API 15초 타임아웃 이슈"

### 📅 발생 일시
- **발견일**: 2026-06-03
- **영향 범위**: 프론트엔드 시장 헤더 및 백엔드 시장 개요 API (`MarketHeader.tsx`, `router_market.py`)
- **GitHub Issue**: [#1 bug: MarketHeader 시장 개요 API 15초 타임아웃 발생](https://github.com/CarpediemBDev/stockAuto/issues/1)

### 🔍 현상 (Symptom)
- 프론트 콘솔에 `Failed to fetch market overview: timeout of 15000ms exceeded` 오류가 발생함.
- 시장 헤더가 `/api/v1/market/overview` 응답을 받지 못해 NASDAQ, USD-KRW, 시장심리 갱신에 실패함.

### 🕵️ 근본 원인 (Root Cause)
- `/api/v1/market/overview` 하나가 시장심리(`QQQ`), NASDAQ(`^IXIC`), USD-KRW(`USDKRW=X`)를 모두 조회함.
- 세 값 모두 yfinance 외부 데이터에 의존하며, Yahoo 호출 안정화를 위한 전역 락/캐시 구조 때문에 외부 조회가 지연되면 전체 API 응답이 프론트 Axios 기본 타임아웃 15초를 넘을 수 있음.
- UI 표시용 API인데도 일부 지표 지연이 전체 응답 실패로 전파되는 구조였음.

### 🛠️ 해결 조치 (Resolution)
- **수정 파일**:
  - `backend/app/trades/router_market.py`
  - `frontend/lib/api.ts`
- **수정 내용**:
  - 시장심리/NASDAQ/USD-KRW 각각에 서버 측 개별 타임아웃을 적용함.
  - 일부 지표가 늦거나 실패해도 전체 API 실패 대신 부분 응답을 반환하도록 변경함.
  - 시장심리 실패 시 `NEUTRAL`, NASDAQ/USD-KRW 실패 시 `null` fallback을 사용함.
  - 프론트에서는 `marketAPI.getOverview()` 호출에만 30초 타임아웃을 적용함.

### 🧠 재발 방지 교훈
- 외부 API에 의존하는 UI 표시용 엔드포인트는 전체 실패보다 부분 실패 허용 구조를 우선 적용한다.
- 여러 외부 지표를 한 응답에 묶는 경우, 프론트 타임아웃 증가만으로 해결하지 말고 백엔드에서 개별 작업 시간 제한과 fallback을 먼저 설계한다.
- 동일 증상 발생 시 `/api/v1/market/overview`의 전체 응답 시간과 개별 지표 fallback 여부를 먼저 확인한다.

---

## [Bug-003] "SIMULATED 자동매매 매도 경로 StaleDataError 사이클 중단 이슈"

### 📅 발생 일시
- 발견일: 2026-07-11
- 영향 범위: 백엔드 스케줄러 매도 실행 경로 (`scheduler.py` `micro_session` / `process_exit_signals`)

### 🔍 현상 (Symptom)
- trade_mode 스냅샷 핫픽스로 `process_exit_signals`의 `db_settings` DetachedInstanceError가 제거되자, 그다음 단계인 SIMULATED 매도 실행의 `db.merge(h)`에서 `sqlalchemy.orm.exc.StaleDataError: Version id '1' ... does not match existing version '2'`가 발생함.
- `run_user_trading_flow`의 광역 except가 이를 삼켜 매도 사이클이 통째로 중단되고, 같은 사이클의 매수(`process_entry_signals`)까지 스킵됨. SIMULATED은 브로커 `sell_order`를 먼저 호출한 뒤 `merge`에서 죽으므로 "브로커 매도됨/DB 미반영" 불일치 위험까지 있었음.

### 🕵️ 근본 원인 (Root Cause)
- `micro_session`은 진입 때마다 `ctx.holdings` 전체를 기본값 `db.merge(h)`(load=True)로 auto-merge해 재조정한다.
- `process_exit_signals`는 `last_price`/`highest_price`를 version_id 낙관적 잠금과 간섭하지 않도록 Core 컬럼 단위 bulk-UPDATE로 DB에만 반영하려 했다.
- 그러나 관측값을 공유 detached holding의 매핑 컬럼에도 세팅해 h가 dirty가 되고, 다음 auto-merge(load=True)가 이 diff를 flush하며 (1) Core UPDATE로 쓴 값을 되돌리고 (2) `version_id`를 1→2로 올린다. Core UPDATE로 version 간섭을 피하려 한 의도를 auto-merge가 무력화한 것.
- 이후 Part B 매도가 여전히 stale 원본(v1)을 `db.merge(h)`하며 DB(v2)와 불일치해 StaleDataError 발생. 조기 중단으로 한 사이클 2종목 이상 매도 시 삭제된 holding이 `ctx.holdings`에 남아 다음 auto-merge를 오염시키는 2차 잠복 버그까지 가려두고 있었음.

### 🛠️ 해결 조치 (Resolution)
- 수정 파일: `backend/app/bot/scheduler.py`
- `micro_session`의 holdings auto-merge를 `db.merge(h, load=False)`로 변경 — DB 재조정 flush를 원천 제거해 Core UPDATE 값 되돌림·version 상승을 막음. 병합 이후의 실제 변경(수량 증감·delete)은 그대로 dirty 추적·flush됨.
- `process_exit_signals`가 관측값(`last_price`/`highest_price`)을 공유 holding 매핑 컬럼에 세팅하지 않고 로컬 변수로만 다루도록 정리(DB 반영은 Core UPDATE 유지).
- 전량 매도(delete)된 holding을 `ctx.holdings`에서 즉시 제거해 다음 auto-merge의 삭제분 재병합·유령 재삽입 차단.
- trade_mode 스냅샷 핫픽스와 결합: 위 수정이 version 상승을 없애므로 `expire_on_commit=False`(세션 밖 holding 속성 접근 보장)를 유지해도 StaleData가 재발하지 않음.
- 검증: 회귀 테스트 `backend/tests/test_scheduler_detached_snapshot.py`가 두 종목 전량 매도 성사(sell_calls==2, 잔여 holdings==0)를 고정. `python scripts/verify_harness.py` 통과.

### 🧠 재발 방지 교훈
- 하나의 ORM 행에 Core bulk-UPDATE(version 비간섭)와 ORM 재-merge(load=True)를 혼용하면 세션 밖 객체가 DB와 diverge해 값 되돌림·version 상승을 유발한다. 읽기용 재부착은 `merge(load=False)`, 실제 영속은 명시적 `merge`로 역할을 분리한다.
- 세션 경계를 넘나드는 ORM 객체를 컨텍스트에 장기 보관하는 패턴(`ctx.holdings`)은 삭제/수량변경 후 스냅샷 정합성을 함께 갱신해야 한다. (근본 해소는 HoldingView DTO 전환 — 후속 과제)
- 광역 except가 StaleData 같은 정합성 오류를 삼켜 사이클을 조용히 중단시키면 하위 잠복 버그가 가려진다. 정합성 예외는 조기에 드러내고 회귀 테스트로 고정한다.
