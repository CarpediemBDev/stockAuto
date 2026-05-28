# [구현 계획서] Phase 27: 누적 데이터 분석 기반 내일 상승 예측 스윙 스캐너 (Next-Day Breakout Predictor)

본 계획서는 현재 15분봉 단기 모멘텀에 의존하는 스캐너를 넘어, **"세력이 본격적으로 움직이기 직전(주가 수렴 및 거래량 급감 구역)의 누적 데이터를 분석하여 내일 폭발할 종목을 포착하는 스윙 매집 스캐너 엔진"**을 구축하는 설계안입니다.

## 사용자 검토 요구사항

> [!IMPORTANT]
> **핵심 매커니즘: 돌파 직전의 변동성/거래량 수렴 포착 (VCP & Volume Dry-up)**
> 15분봉의 단기 스파이크(세력 감지)에 추격 매수하는 것이 아니라, **최근 60~120일 동안의 일봉 누적 데이터**를 활용해 매집이 완료되고 내일 당장 솟구칠 수 있는 '임계점'에 도달한 종목을 진단합니다.
> 
> 1. **변동성 및 거래량 수축(VUD) 공식 고도화**:
>    - 가격 진폭이 극도로 좁아진 수축 구역 포착 (Minervini VCP 수렴 규칙)
>    - 당일 거래량이 최근 20일 평균 거래량의 30% 이하로 메마른 상태 검증 (매도 물량 씨 마름 감지)
> 
> 2. **OBV 누적 매집 다이버전스 (OBV Accumulation Divergence)**:
>    - 주가는 평평하거나 약조정을 거치는 반면, OBV 누적선은 지난 5~10일간 꾸준히 고점을 높여가는 "세력의 몰래 매집 패턴" 공식 탑재.
> 
> 3. **볼린저 밴드 밀착 (Bollinger Band Squeeze)**:
>    - 일봉 볼린저 밴드 폭(Band Width)이 최근 120일 최저 수준으로 조여져 에너지가 한곳으로 응축된 종목 선별.
> 
> 4. **내일 상승 예측 스코어 (Next-Day Breakout Score)**:
>    - 상기 조건들을 조합해 **0~100점 만점**의 확률 점수를 계산하고, 최상위 종목을 대시보드에 노출.

---

## 제안된 변경 사항

### [Component 1] 퀀트 분석 지표 확장

#### [MODIFY] [indicators.py](file:///d:/dev/workspace/stockAuto/backend/app/scanner/indicators.py)
* **신규 지표 수식 추가:**
  - `calculate_volume_dryup(df, window=20)`: 최근 평균 거래량 대비 당일 거래량이 메마른 비율(VUD) 연산.
  - `calculate_obv_divergence(df, window=10)`: 주가 흐름과 OBV의 누적 다이버전스 일치 여부 및 기울기 계산.
  - `calculate_bb_squeeze(df, window=20)`: 볼린저 밴드 대폭 수축(Squeeze) 여부 및 밴드폭 지표 계산.

---

### [Component 2] 내일 상승 예측 스윙 스캐너 코어 개발

#### [NEW] [swing_predictor.py](file:///d:/dev/workspace/stockAuto/backend/app/scanner/swing_predictor.py)
* **역할:** 누적 일봉 데이터를 분석하여 내일 돌파 상승 가능성이 90% 이상인 종목을 진단하고 점수를 산출합니다.
* **주요 메서드:**
  - `async def analyze_swing_setup(ticker: str) -> dict`: 단일 종목의 120일 누적 일봉을 가져와 VCP, 거래량 극감, OBV 다이버전스, BB 스퀴즈를 종합 채점.
  - `async def scan_next_day_candidates(tickers: list) -> list`: 감시 대상 종목군 전체를 병렬 스캔하여 내일 상승 확률이 가장 높은 Top 5 후보 선별 및 점수 산출.

---

### [Component 3] 시스템 라우터 및 프론트엔드 UI 연동

#### [MODIFY] [router.py](file:///d:/dev/workspace/stockAuto/backend/app/scanner/router.py)
* **신규 API 엔드포인트 개설:**
  - `@router.get("/swing-predict")`: 내일 상승 예측 스윙 종목 TOP 5 분석 결과와 채점 리포트를 프론트엔드로 전달하는 API 구현.

#### [NEW] [SwingPredictorCard.tsx](file:///d:/dev/workspace/stockAuto/frontend/components/SwingPredictorCard.tsx)
* **UI 기능:**
  - Next.js 기반 프리미엄 다크 테마 카드 UI 신설.
  - 종목별 **'내일 상승 예측 점수 (Next-Day Score)'**를 화려한 프로그레스 바(ProgressBar)로 시각화.
  - VCP 수축 여부, 거래량 극감(Volume Dry-up) 상태, OBV 다이버전스 강도를 배지(🟢/🔴)로 한눈에 모니터링 가능하도록 구현.

#### [MODIFY] [Dashboard.tsx](file:///d:/dev/workspace/stockAuto/frontend/components/Dashboard.tsx)
* 신설된 `SwingPredictorCard` 컴포넌트를 대시보드 레이아웃에 통합 적재하여 종합 모니터링이 가능하도록 화면 배치.

---

## 검증 계획

### 자동화 테스트
1. `pytest` 또는 가상 테스트 스크립트를 통해 `swing_predictor.py`가 실제 120일 일봉 데이터를 정상적으로 수집(DataProvider 연동)하는지 검증합니다.
2. VCP 수축 공식 및 OBV 다이버전스 알고리즘이 NaN 오류 없이 정확하게 0~100점 점수를 뱉어내는지 백엔드 문법 검증(`py_compile`)을 실시합니다.

### 수동 검증
1. 프론트엔드 대시보드에 **"내일 세력 돌파 예측 (Next-Day Swing Breakout)"** 카드가 정상적으로 노출되며 실시간 점수 게이지바가 렌더링되는지 브라우저에서 최종 확인합니다.
