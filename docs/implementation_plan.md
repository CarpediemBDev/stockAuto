# 🏆 [구현 계획서] 모놀리식 전략 코드의 객체 지향 전략 패턴 (Strategy Pattern) 정밀 리팩토링

본 계획서는 `scanner.py`, `backtest_engine.py`, `scheduler.py` 내부 깊숙이 기입된 14대 모놀리식 조건 분기형 전략 코드들을 완전 객체 지향 수준인 **전략 패턴 (Strategy Pattern)** 구조로 해체/격리하고 조립함으로써, 백테스트와 실시간 거래 논리를 100% 동치시키고 향후 새로운 전략 카드를 레고 블록처럼 손쉽게 꽂아서 쓸 수 있는 고도화된 아키텍처 리팩토링 계획입니다.

---

## 🚨 사용자 검토 요구사항 (User Review Required)

> [!IMPORTANT]
> **전략 패턴 추상 인터페이스 설계의 핵심 사양**
> 1. **통합 인터페이스 (`BaseStrategy`)**:
>    - `calculate_score(row, regime, is_entry) -> float`: 모든 전략의 공통 채점 로직 추상화. pandas Series(백테스트) 및 dict(실시간 스캐너) 모두 호환되도록 설계.
>    - `get_initial_entry_factor(regime) -> float`: 전략별 진입 정찰병 비중 결정 (예: 일반 0.15, 폭발형 1.0)
>    - `get_pyramid_trigger(stage) -> float`: 전략별 피라미딩(불타기) 트리거 수익률 (예: 일반 2%/4%, 전략 B 3%/6%)
>    - `get_stop_loss_pct(atr, price) -> float`: 전략별 동적 손절선 계산 (일반 3% / 1.5x ATR, 폭발형 6% / 3.0x ATR)
>    - `get_trailing_stop_pct(atr, price) -> float`: 전략별 동적 트레일링 스탑 계산 (일반 2% / 1.0x ATR, 폭발형 4% / 2.0x ATR)
>    - `base_allocation_pct`: 전략별 기본 자본 분할 단위 (일반 0.40, 전략 A 0.10)
>    - `min_allocation_usd`: 최소 자본 할당액 (일반 $2000.0, 전략 A $0.0)
>    - `min_smart_exit_profit`: 스마트 익절 최소 마진 (일반 2.5%, 전략 A/B 1.0%)
> 
> 2. **동적 팩토링 도입 (`strategy_factory.py`)**:
>    - 문자열 설정 상수(`settings.STRATEGY_TYPE`)를 받아 해당하는 전략 인스턴스를 즉각 동적으로 생성 및 매핑해주는 팩토리 탑재.

---

## 📋 전략 패턴 아키텍처 설계

신설할 `backend/app/strategies/` 모듈의 구조도입니다:

```
backend/app/strategies/
├── __init__.py             # 패키지 선언 및 간편 임포트 제공
├── base_strategy.py        # 전략 인터페이스 정의 (추상 베이스 클래스)
├── strategy_factory.py     # 동적 팩토리 클래스 (레고 블록 변환기)
├── regime_switching.py     # [🏆 통합 1위] 마스터 레짐스위칭
├── senior_simple.py        # 시니어 단순화 (Strategy S)
├── strategy_a.py           # 태초의 방패 (Strategy A)
├── strategy_b.py           # 채점 분리 과도기 (Strategy B)
├── strategy_c.py           # 손익비 최적화 v2.0 (Strategy C)
├── exploded_c.py           # 즉시 풀비중 C-폭발형
└── qullamaggie.py          # 쿨라매기 단독 전략
```

---

## 🛠️ 제안된 변경 사항 (Proposed Changes)

### [Component 1] 전략 모듈 신설
#### [NEW] [base_strategy.py](file:///d:/dev/workspace/stockAuto/backend/app/strategies/base_strategy.py)
* 추상 베이스 클래스 `BaseStrategy` 정의. 공통 파라미터(Allocation, ATR, Smart Exit Margin)의 디폴트값 정의 및 `calculate_score` 추상 메서드 제공.

#### [NEW] [strategy_factory.py](file:///d:/dev/workspace/stockAuto/backend/app/strategies/strategy_factory.py)
* `get_strategy(strategy_type: str) -> BaseStrategy` 구현을 통해 문자열과 매핑 클래스 동적 연동.

#### [NEW] [개별 전략 파일들](file:///d:/dev/workspace/stockAuto/backend/app/strategies/)
* `regime_switching.py`, `senior_simple.py`, `strategy_a.py`, `strategy_b.py`, `strategy_c.py`, `exploded_c.py`, `qullamaggie.py` 등 핵심 전략 개별 파일 격리 구현.

---

### [Component 2] 백테스트 엔진 리팩토링
#### [MODIFY] [backtest_engine.py](file:///d:/dev/workspace/stockAuto/backend/app/bot/backtest_engine.py)
* 백테스터 생성 시 `strategy_factory.get_strategy(strategy_type)`를 호출하여 주입.
* `_calculate_score` 메서드 내부의 500줄 가량의 거대한 if-else 분기 삭제 ➔ `self.strategy.calculate_score(row, regime, is_entry)` 1줄로 단축.
* 손절선, 트레일링 스탑, 비중 조절 로직 역시 `self.strategy`가 리턴하는 동적 변수로 일괄 대체하여 백테스트 루프 간결화.

---

### [Component 3] 실시간 스캐너 및 스케줄러 리팩토링
#### [MODIFY] [scanner.py](file:///d:/dev/workspace/stockAuto/backend/app/scanner/scanner.py)
* 실시간 채점 시 `strategy_factory.get_strategy(settings.STRATEGY_TYPE)`를 싱글톤 또는 동적으로 가져와 `calculate_score(cand, sentiment, is_entry=True)` 호출로 전면 개편.
* 200줄 규모의 분기문 제거 완료.

#### [MODIFY] [scheduler.py](file:///d:/dev/workspace/stockAuto/backend/app/bot/scheduler.py)
* 포지션 청산 및 스마트 익절 판독 시, `strategy` 객체의 `min_smart_exit_profit`을 사용하도록 실시간 파라미터 주입으로 개편.

---

## 🧪 검증 계획 (Verification Plan)

### 자동 컴파일 및 린트 검증
1. 백엔드 컴파일 무결성 검증:
   ```bash
   python -m py_compile app/strategies/*.py app/bot/backtest_engine.py app/scanner/scanner.py app/bot/scheduler.py
   ```
   * 오류 검출이 없을 때까지 자가 치유(Self-Correction) 반복 가동.

### 백테스트 정밀 검증 (PnL 정합성 확보)
2. 리팩토링 전/후 백테스트 결과가 정확히 일치하는지 검증:
   ```bash
   python run_tournament.py
   ```
   * 리팩토링 후에도 동일 장세에서 `마스터 레짐스위칭` 전략이 `+21.72%` (Q2) 및 동일한 거래 횟수로 정확하게 똑같이 구현되는지 정밀 체크.
