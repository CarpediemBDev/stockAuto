# 카나리아 배분 전략 라이브 이식 설계 (canary_allocation)

> 상태: **S1~S4 구현 완료(2026-10-05, 브랜치 `feat/canary-allocation`), S5 관측 계정 가동은 별도 승인 대기** · 작성일: 2026-10-04 · 소유 주제: 크로스에셋 카나리아 전략의 라이브(SIMULATED) 이식 설계
> 상위 규칙 충돌 시 `AGENTS.md` 우선. 성과 판정 원장은 [`../strategy_alpha_verdict.md`](../strategy_alpha_verdict.md), 연구 경과는 [`../tasks/2026-10-04.md`](../tasks/2026-10-04.md).
> 구현 결과와 설계 대비 변경점은 §10에 기록한다.

---

## 0. 요약

| 항목 | 결정 |
| :--- | :--- |
| 전략 키 | `canary_allocation` (전략 1개 = `.py` 1개 = `strategies` 행 1개) |
| 성격 | 자율 슬롯(`is_autonomous=True`) + **목표비중형**(신규 플래그 `is_target_weight=True`) |
| 판단 | **월 1회**, 월말 완결 일봉 기준. 다음 정규장에서 집행 |
| 신호 | 카나리아 7개 양호 비율 = QQQ 비중 (0, 1/7, …, 1) |
| 보유 자산 | QQQ + 방어자산(IEF 또는 BIL) — **레버리지 없음(1x)** |
| 매매 빈도 | 연 약 7~8회 (밴드 10%p) |
| 실행 모드 | SIMULATED 전용 (기존 자율 경로와 같은 제약) |
| 신규 스키마 | `autonomous_slot_states` 테이블 1개 (월별 결정 기록) |
| 기대 성과(연구, 세후 5천만원) | 2005~ 연 11.9% / Sharpe 1.00 / MDD −18% (QQQ 14.1% / 0.77 / −53%) |
| 알려진 약점 | 닷컴형 기술주 거품 붕괴 MDD −62%, 30년 세후 수익은 QQQ보다 연 약 4%p 낮음 |

**왜 1x인가:** 1.5배 변형은 2005년 이후 성과가 더 좋았지만 닷컴형 위기에서 MDD −81~−89%였다(연구 §11~§12). 방어형 목적에 맞지 않는다.

---

## 1. 전략 규칙 (SSOT — 라이브·백테스트 공통)

### 1.1 신호 7개
모든 가격은 **수정 종가(배당·분할 반영) 일봉**이다. 13612U(p) = 평균(p/p[−21]−1, p/p[−63]−1, p/p[−126]−1, p/p[−252]−1).

| # | 신호 키 | 정의 | 양호 조건 | 의미 |
| :-- | :--- | :--- | :--- | :--- |
| 1 | `vwo` | VWO 13612U | > 0 | 신흥국 위험선호 |
| 2 | `agg` | AGG 13612U | > 0 | 금리·채권 충격 부재 |
| 3 | `smh_spy` | (SMH/SPY) 비율의 13612U | > 0 | 반도체 상대강도 |
| 4 | `xhb` | XHB 13612U | > 0 | 주택·실물 경기 |
| 5 | `xlf_spy` | (XLF/SPY) 비율의 13612U | > 0 | 은행·신용 건전성 |
| 6 | `nfci` | FRED `NFCI`(주간) | 판단일 기준 값 ≤ 직전 252거래일 평균 | 금융여건 |
| 7 | `sox` | `^SOX` 13612U | > 0 | 반도체 경기(닷컴형 보조) |

- **NFCI 발표 지연**: FRED 관측일은 주 마감 금요일, 발표는 다음 주 수요일이다. 판단일 D에는 **관측일 ≤ D − 5영업일**인 값만 사용한다(연구와 동일 가정).
- **월말 판단일**: 그 달 마지막 **완결** 미국 정규장 거래일(ET 기준). 당일 미완결 봉은 제외한다(`process_autonomous_slots`의 기존 규칙과 동일).

### 1.2 목표 비중
```
E = (양호 신호 수) / 7
목표 = { QQQ: E,  방어자산: 1 − E }
방어자산 = IEF  (IEF 13612U > BIL 13612U 이면)
         = BIL  (그 외)
```

### 1.3 밴드 (회전 억제)
- 직전 **확정 목표**와 새 목표의 비중 차이 합 Σ|w_new − w_last| < 0.10 이면 **직전 목표를 유지**하고 매매하지 않는다.
- 비교 기준은 **실제 보유 비중이 아니라 직전 확정 목표**다(연구 백테스트와 동일). 실제 비중은 한 달 동안 시세에 따라 표류하지만, 표류만으로는 매매하지 않는다.
- 결과적으로 신호 1개 변화(1/7 = 14.3%p)는 항상 밴드를 넘고, 방어자산 IEF↔BIL 교체도 밴드를 넘는다.

### 1.4 데이터 결측 정책 (안전측)
- 7개 신호 중 **하나라도 계산할 수 없으면 그 달은 판단하지 않고 직전 목표를 유지**한다.
- 일부 신호만으로 비율을 계산하면 조용히 다른 전략이 된다. `macro_data.fetch_macro_series`의 "하나라도 결손이면 None" 원칙과 같다.
- 결측이 3영업일 넘게 이어지면 WARNING 로그와 텔레그램 알림을 보낸다(쿨다운 적용).
- 단, **수집 실패·결측은 상태 행을 만들지 않고 다음 사이클에 재시도**한다. 일시적 네트워크 장애로 한 달 판단 전체를 잃지 않기 위함이다(§10).

---

## 2. 코드 구조

### 2.1 신규 파일

| 파일 | 역할 |
| :--- | :--- |
| `backend/app/strategies/canary_allocation.py` | `CanaryAllocation(BaseStrategy)`. **순수 함수**로 신호·목표비중 계산(SSOT). 네트워크·DB 접근 없음 |
| `backend/app/bot/target_weight_executor.py` | 라이브 집행부 `process_target_weight_slots(ctx, slot_allocations)`. 목표 대비 차이 주문 |
| `backend/app/bot/canary_data.py` (또는 `scanner/data_provider` 확장) | 신호 입력 수집: yfinance 일봉 9종(VWO, AGG, SMH, SPY, XHB, XLF, ^SOX, IEF, BIL) + FRED NFCI |
| `backend/alembic/versions/<rev>_add_autonomous_slot_states.py` | 상태 테이블 생성 |
| `backend/alembic/versions/<rev>_seed_canary_allocation.py` | `strategies` 행 시딩(`b8e4f6a2c913` 패턴) |
| `backend/tests/test_canary_allocation.py` 외 | §6 참조 |

### 2.2 전략 클래스 인터페이스 (안)

```python
class CanaryAllocation(BaseStrategy):
    is_autonomous = True        # 스캐너 진입·손절/트레일링 파이프라인 면제 (scheduler.py:1708, 2466 기존 분기 재사용)
    is_target_weight = True     # IN/OUT 경로(process_autonomous_slots)가 아닌 목표비중 경로로 집행
    SIGNAL_TICKERS = ("VWO", "AGG", "SMH", "SPY", "XHB", "XLF", "^SOX")
    HOLD_TICKERS = ("QQQ", "IEF", "BIL")
    BAND = 0.10

    def compute_signals(self, closes: dict[str, pd.Series], nfci: pd.Series, as_of: date) -> dict[str, bool] | None
        # as_of까지의 완결 데이터만 사용. 하나라도 계산 불가면 None.
    def compute_target(self, signals: dict[str, bool], closes: dict[str, pd.Series], as_of: date) -> dict[str, float]
        # {"QQQ": E, "IEF" or "BIL": 1-E}
    def apply_band(self, new: dict[str, float], last: dict[str, float] | None) -> tuple[dict[str, float], bool]
        # (확정 목표, 변경 여부)
    def compute_target_series(self, closes, nfci, month_ends) -> pd.DataFrame
        # 백테스트용: 월말마다 위 3단계를 전방 패스로 적용 (라이브와 동일 함수 재사용)
```
- `calculate_score`는 기존 자율 전략처럼 항상 0점(미발화)이다.

### 2.3 기존 파일 수정 (최소)

| 파일 | 변경 |
| :--- | :--- |
| `app/strategies/strategy_factory.py` | `"canary_allocation"` 분기 추가 |
| `app/bot/multi_strategy_manager.py` | 프리픽스 맵에 `"canary_allocation": "CA_"` |
| `app/bot/scheduler.py` | ① `process_autonomous_slots`에서 `is_target_weight` 전략은 `continue`(IN/OUT 경로 진입 금지) ② `process_autonomous_slots` 호출 직후 `process_target_weight_slots` 호출 **1줄**. 집행 로직은 새 모듈에 둔다 |
| `app/backtests/backtest_engine.py` | `_run_autonomous` 앞에서 `is_target_weight`이면 `_run_target_weight()`로 분기 (§4) |
| `app/admin/backtest_runner.py` | `autonomous_specs`에 `("canary_allocation", None)` — 다자산이라 자산 티커 단일값 대신 전략이 유니버스를 선언 |
| `app/core/models.py` | `AutonomousSlotState` 모델 |
| `locales/ko.json`, `locales/en.json` | 전략명, 텔레그램 리밸런싱 메시지 키 |
| `app/translations/` | 전략명 번역 |

> ⚠️ **동시 작업 충돌 주의 (2026-10-04 관측):** 다른 세션이 `scheduler.py`, `system_settings.py`를 미커밋 수정 중이고 `gap_exit.py`를 새로 추가했다. 구현 착수 시 해당 작업의 병합 여부를 먼저 확인하고, `scheduler.py` 변경은 위 2곳으로 한정해 충돌면을 최소화한다. 구현은 별도 worktree에서 한다(`AGENTS.md §9-1`).

---

## 3. 라이브 집행 설계 (`process_target_weight_slots`)

### 3.1 상태 테이블 `autonomous_slot_states`

| 컬럼 | 타입 | 설명 |
| :--- | :--- | :--- |
| `id` | Integer PK | |
| `user_id` | FK users (CASCADE) | |
| `slot_key` | String | 예: `canary_allocation` |
| `decision_date` | Date | 판단에 쓴 월말 완결 거래일 |
| `target_json` | Text(JSON) | 확정 목표 `{"QQQ":0.571,"BIL":0.429}` |
| `signals_json` | Text(JSON) | 신호 7개 값 + 입력 날짜(감사용) |
| `status` | String | `DECIDED` → `EXECUTING` → `DONE` / `HELD`(데이터 결측·밴드 유지) |
| `updated_at` | AwareDateTime | |
| 유니크 | (`user_id`, `slot_key`, `decision_date`) | 같은 달 중복 판단 차단 |

- **재기동 안전**: 판단 결과를 DB에 남기므로, 서버를 재기동해도 같은 달을 다시 판단하거나 이중 주문하지 않는다.
- 마이그레이션은 `create_table` / `drop_table`만 쓴다(데이터 변경 없음, `check_migration_safety.py` R1~R4 비해당).

### 3.2 사이클 흐름 (1분 루프마다 호출, 멱등)

```
1. 대상 슬롯 = is_target_weight 전략 슬롯. SIMULATED가 아니면 경고 후 skip(쿨다운).
2. 최근 월말 완결 거래일 D 계산.
3. state(D) 조회
   - 없음 → 신호 계산
       · 결측 → status=HELD 기록, 직전 목표 유지, 종료
       · 정상 → 밴드 적용 → 변경 없음: status=HELD(목표=직전) / 변경: status=DECIDED
   - DONE/HELD → 종료 (이번 달 할 일 없음)
   - DECIDED/EXECUTING → 4로
4. 정규장(REGULAR)이 아니면 대기 로그(쿨다운) 후 종료.
5. 미체결 가상주문(UnfilledOrder)이 이 슬롯 티커에 남아 있으면 종료(다음 사이클 재시도).
6. 차이 주문 계산: 슬롯 총자산 V(현금+평가액) 기준
     목표수량[t] = floor(V × w[t] × 0.98 / 현재가[t])   (0.98 = 기존 자율 경로와 같은 현금 버퍼)
     차이 = 목표수량 − 보유수량
7. status=EXECUTING. 매도 먼저(차이<0), 그다음 매수(차이>0). 종목별 Redis 심볼 락(acquire_symbol_order_lock).
   - 매도: 부분 매도면 Holding.quantity 차감, 전량이면 delete_holding. TradeLog(SELL, realized_pnl=calculate_realized_pnl).
   - 매수: 기존 보유가 있으면 평단 갱신, 없으면 신규 Holding(strategy_type=slot_key).
   - 어느 주문이든 미체결/실패면 즉시 중단 → 다음 사이클에서 6부터 재계산(남은 차이만 주문).
8. 모든 차이가 1주 미만이면 status=DONE + 텔레그램 리밸런싱 요약(신호 7개, 이전→새 비중).
```

### 3.3 기존 공통 함수 재사용과 주의점
- `record_successful_buy`(`scheduler.py:2479`)는 추가 매수 시 "Pyramiding Stage" 로그를 남기고 `buy_stage`를 바꾼다. 목표비중 슬롯에서는 의미가 맞지 않으므로 **전용 기록 함수**를 두거나, 해당 함수에 로그 문구 파라미터를 추가한다. 어느 쪽인지는 구현 시 결정한다(중복 구현 금지 원칙상 후자 우선 검토).
- 매도 기록은 `process_autonomous_slots`의 매도 블록(`scheduler.py:1047~1105`)과 같은 계산(`calculate_realized_pnl`, `delete_holding`)을 쓴다. 공통 헬퍼로 추출해 두 경로가 함께 쓰는 것이 SSOT상 바람직하다.
- 슬롯 자본 계산(`MultiStrategyManager.calculate_slots_allocation`)은 `Holding.strategy_type == slot_key`로 합산하므로, QQQ·IEF·BIL 보유분 모두 `strategy_type="canary_allocation"`으로 저장해야 한다.
- 손절·트레일링 면제는 기존 `is_autonomous` 분기(`scheduler.py:1708`)가 처리한다. 신규 진입 면제(`scheduler.py:2466`)도 같다.

### 3.4 정수 주식 영향
- QQQ 1주 ≈ $740. 슬롯 $10,000이면 비중 해상도가 약 7.4%p다. 연구의 정수 주식 시뮬레이션에서 $5k~$50k 사이 결과 차이는 미미했다(§2.3).
- 슬롯 총자산 $3,000 미만이면 QQQ 비중을 제대로 표현할 수 없으므로 WARNING 후 집행하지 않는다(임계값은 구현 시 상수화).

---

## 4. 백테스트 패리티 (`_run_target_weight`)

- 일봉(1d) 전용. 유니버스 = `SIGNAL_TICKERS ∪ HOLD_TICKERS`. NFCI는 `macro_data`의 FRED 수집 함수로 받는다(§5).
- 전략의 `compute_target_series`로 월말 목표를 **한 번** 계산하고, 매 봉에서 **직전 판단일 확정 목표**를 다음 봉 가격으로 집행한다(룩어헤드 차단, 라이브와 동일).
- 체결은 정수 주식, 수수료 `settings.SIMULATED_FEE_RATE`(0.10%), SEC fee는 엔진 기존 규칙을 따른다.
- **패리티 기준**: 연구 스크래치 결과(2005-01~2026-09, 1x)와 비교해 연복리 ±0.5%p, MDD ±2%p 이내. 차이는 정수 주식·현금 이자 처리·SEC fee에서만 나와야 한다.

| 연구 기준값 (세전, 소수 비중) | 연복리 | Sharpe | MDD | 매매/년 |
| :--- | ---: | ---: | ---: | ---: |
| 2005~2015 | 11.5% | 1.07 | −14% | 8.2 |
| 2016~ | 17.9% | 1.34 | −17% | 8.3 |

---

## 5. 데이터 조회

| 입력 | 원천 | 조회 | 캐시 |
| :--- | :--- | :--- | :--- |
| VWO, AGG, SMH, SPY, XHB, XLF, ^SOX, IEF, BIL, QQQ | yfinance 일봉 (`fetch_ohlcv(t, "1d", "2y")`) | 13612U에 252봉 + 여유 필요 → **`period="2y"`면 충분**(약 500봉) | 기존 OHLCV 캐시(10초)는 짧다. 월 1회 판단이므로 판단 시점에만 조회하고, 결과는 상태 테이블에 남긴다 |
| NFCI | FRED CSV (키 불필요) | `macro_data._fetch_series("NFCI")` 재사용. 252거래일 평균에 약 1.2년 필요 → 전체 시리즈 수신 | `macro_data`에 **별도 함수** `fetch_fred_series(series_id)` 추가(캐시 6시간). 기존 `MACRO_SERIES` 튜플은 "교체 금지" 주석이 있으므로 건드리지 않는다 |

- **수정 종가 확인**: `fetch_ohlcv`는 `yf.download` 기본값을 쓴다. 현행 yfinance 기본값은 `auto_adjust=True`지만, 구현 시 명시적으로 고정하고 테스트로 못박는다(배당 반영 여부가 13612U 부호를 바꿀 수 있음).
- `^SOX`처럼 `^` 지수 심볼이 기존 경로에서 정상 동작하는지 구현 첫 단계에서 확인한다.

---

## 6. 테스트 계획

| 테스트 | 검증 내용 |
| :--- | :--- |
| 신호 단위 | 13612U 계산, 비율 신호, NFCI 지연·평균, **판단일 이후 데이터 미사용**(미래 봉을 붙여도 결과 불변) |
| 결측 정책 | 신호 1개 결측 → None → HELD, 직전 목표 유지 |
| 목표·밴드 | E=4/7 → QQQ 0.571, IEF/BIL 선택, 밴드 경계(0.0999 유지 / 0.1001 변경) |
| 집행 | 매도→매수 순서, 부분 매도 수량 차감, 미체결 시 중단 후 재개, 같은 달 이중 주문 없음, 재기동 후 상태 복원 |
| 격리(멀티테넌시) | 사용자 2명이 서로 다른 목표·보유를 가질 때 슬롯 자본·상태가 섞이지 않음 |
| 슬롯 자본 | QQQ·IEF·BIL 보유가 모두 같은 슬롯 평가액으로 합산 |
| 백테스트 패리티 | §4 기준값 대비 허용오차 |
| 회귀 | 기존 `test_leveraged_regime.py`, `test_backtest_autonomous.py` 무변경 통과(IN/OUT 경로 비영향) |

검증 순서: 단위 → 백테스트 패리티 → `python scripts/verify_harness.py` → 관측 계정 배치.

---

## 7. 단계별 실행 계획

| 단계 | 내용 | 완료 조건 |
| :--- | :--- | :--- |
| S1 | 전략 클래스(순수 함수) + 신호 단위 테스트 | 룩어헤드·결측 테스트 통과 |
| S2 | 백테스트 경로 `_run_target_weight` + 패리티 테스트 | 연구 기준값 허용오차 이내 |
| S3 | 상태 테이블 마이그레이션 + 전략 시딩 + 팩토리/프리픽스/번역 | `alembic upgrade/downgrade` 왕복 |
| S4 | 라이브 집행부 + 스케줄러 연결 2곳 | 집행·격리·재기동 테스트, 하네스 통과 |
| S5 | 관측 계정 `obs_canary`(SIMULATED) 생성·가동 | 첫 월말 판단·집행 로그 확인 |
| S6 | 문서 반영 | `strategy_specification.md`, `strategy_map.md`, `SCHEMA.md`, `strategy_alpha_verdict.md §9` |

- S1~S4는 하나의 브랜치/PR(`feat/canary-allocation`)로 묶는다. S5는 운영 작업이라 사용자 승인 후 진행한다.

---

## 8. 운영 판독 기준 (관측 계정)

- 비교 대상: `obs_qqq_hold`(QQQ 보유), `qa_claude`(라이브 레짐 QLD).
- ⚠️ `obs_qqq_hold`는 현재 QQQ 약 78% + 현금 22%다(연구 중 발견). 공정 비교를 위해 **QQQ 100%로 교정하거나 비교 시 0.78배 보정**이 필요하다.
- 월 1회 판단이라 **1년을 돌려도 표본은 12회**다. 라이브로 판정할 수 있는 것은 "배선이 백테스트대로 움직이는가"(신호값·목표비중·체결 수량이 같은 날 백테스트와 일치)이지 성과가 아니다. 성과 판정에는 수년이 필요하다.
- 첫 판단 예시(2026-09-30 데이터 기준): 양호 4/7(VWO·SMH/SPY·NFCI·SOX), 경고 3/7(AGG·XHB·XLF/SPY) → **QQQ 57.1% + BIL 42.9%**(IEF 모멘텀이 BIL보다 약함).

---

## 9. 미해결 위험

1. **표본 외 검증 소진**: 신호 선택에 2005~2026과 닷컴 구간을 모두 썼다. 남은 검증은 실시간 데이터뿐이다.
2. **폭락 2회 의존**: 2005년 이후 우위의 대부분이 2008·2022 회피에서 나왔다.
3. **세금**: 시스템은 양도세를 모델링하지 않는다. 연구 기준 세후에도 Sharpe·MDD 우위는 남지만 수익은 QQQ보다 낮다.
4. **데이터 의존성 증가**: 외부 시계열 10개(yfinance 9 + FRED 1). 하나라도 끊기면 그 달은 판단을 보류한다. 장기 결측 시 대응(수동 판단 등)은 운영 정책으로 정한다.
5. **KIS(실거래) 미지원**: 자율 경로와 같은 이유(주문 인텐트 원장 미배선)로 SIMULATED 전용이다.
6. **동시 세션 충돌**: §2.3 경고 참조.

---

## 10. 구현 결과 (2026-10-05)

| 단계 | 산출물 | 검증 |
| :--- | :--- | :--- |
| S1 전략 | `app/strategies/canary_allocation.py` (순수 함수 SSOT), 팩토리·프리픽스(`CA_`) | `tests/test_canary_allocation.py` 22건. 실데이터 월별 판단 연구 대비 **221/221개월 일치**(2007-03~2026-09, BIL 상장 후 1년치 확보 전 14개월은 판단 보류) |
| S2 백테스트 | `backtest_engine._run_target_weight`, 유니버스 자동 보충, 워밍업 450일, 토너먼트 자율 참가자 등록 | `tests/test_backtest_target_weight.py` 8건. 실데이터 패리티 아래 표 |
| S3 스키마 | `AutonomousSlotState` 모델 + 마이그레이션 `f3a9c2e7d418`(테이블 + 전략 행 시딩), 텔레그램 문구 2종 | 임시 DB에서 upgrade → downgrade → upgrade 왕복 확인(기존 전략 90행 보존), `check_migration_safety` 통과 |
| S4 라이브 | `app/bot/target_weight_executor.py`, `scheduler.py` 변경 5줄(import 1, IN/OUT 경로 제외 3, 호출 1), `macro_data.fetch_fred_series` | `tests/test_target_weight_executor.py` 9건(진입·멱등·매도 선행·밴드 보류·결측 재시도·세션/모드 가드·미체결 재개·2사용자 격리·IN/OUT 비간섭). 네거티브 컨트롤: 매수 선행으로 바꾸면 3건, 밴드 무력화 시 2건 실패 |

**실데이터 엔진 패리티 (2008-07~2026-09, $100k)**

| 구성 | 연복리 | Sharpe | MDD |
| :--- | ---: | ---: | ---: |
| 엔진, 버퍼 0.98 | 15.97% | 1.279 | −14.8% |
| 엔진, 버퍼 1.0 | 16.30% | 1.279 | −15.0% |
| 연구 비중을 같은 체결 방식(월말 리밸런싱·표류)으로 재계산 | 16.34% | 1.283 | −15.0% |
| 연구 원값(일별 고정비중 단순화) | 16.67% | 1.304 | −16.5% |
| QQQ 보유 | 17.47% | 0.834 | −47.0% |

- 같은 체결 방식 기준 차이는 **0.04%p**로 패리티가 확인됐다. §4에 적은 ±0.5%p 기준을 연구 원값과 비교하면 넘는데(−0.7%p), 원인은 버퍼(0.33%p)와 연구 쪽의 일별 리밸런싱 단순화(0.33%p)로 분해됐다.

**설계 대비 변경점**
1. **수량 버퍼 0.98 → 0.995**: 0.98은 BIL·IEF를 포함한 전 비중의 2%를 놀려 연 약 0.3%p를 잃었다. 매수는 집행부가 가용 현금(지정가 +0.1%·수수료 포함)으로 한 번 더 제한한다.
2. **결측 시 상태 미기록**: 설계 초안의 "결측 → HELD 기록"을 "기록 없이 재시도"로 바꿨다(§1.4).
3. **판단 시점**: 정규장 사이클에서만 판단·집행한다. 판단일은 '이번 달 이전의 마지막 거래일'(`latest_decision_date`).
4. **추가 매수 기록**: 기존 `record_successful_buy`를 그대로 재사용했다. 그래서 같은 티커 추가 매수 시 ActionLog에 "Pyramiding Stage 3 Add-on" 문구가 남는다(기능 영향 없음, 표시만 부정확).

**남은 일**
- S5: 관측 계정(SIMULATED) 생성·가동은 사용자 승인 후 진행.
- `obs_qqq_hold`(id 86)의 QQQ 78% 보유 문제는 별도 결정.
- 다른 세션의 미병합 마이그레이션(`e7a2c4d9b153_add_sim_cash_transfers`, 메인 체크아웃 미커밋)이 병합되면 `down_revision` 순서를 맞춰야 한다(같은 부모 `d4e1c8b7f206`이면 다중 head).

