# 🚀 Market Scanner Signal Logic (SIGNAL)

본 문서는 [FILTER.md](file:///d:/dev/workspace/stockAuto/docs/FILTER.md)를 통해 선별된 주도주들을 대상으로, 실제 진입 및 이탈을 위한 정밀한 기술적 시그널 로직을 정의합니다.

---

## 1. 분석 타임프레임 (Multi-Timeframe)
*   **15분봉 (Trend)**: FILTER 조건을 유지하고 있는지 확인 (The Narrative)
*   **5분봉 (Momentum)**: 중간 추세 및 실시간 거래량 변화 확인 (The Confirmation)
*   **1분봉 (Execution)**: VWAP 및 Wick Ratio 기반 정밀 진입/이탈 타점 (The Entry)

---

## 2. 핵심 기술 지표 (Indicators)

| 지표명 | 영문명 | 설명 | 비고 |
| :--- | :--- | :--- | :--- |
| **VWAP** | Volume Weighted Average Price | 거래량 가중 평균가. 기관/세력의 평균 단가로 간주 | **필수** |
| **RVOL** | Relative Volume | 최근 20개 캔들 대비 현재 거래량의 비율 | **최소 2배 이상** |
| **Wick Ratio** | Candle Wick Ratio | 전체 캔들 길이 대비 윗꼬리의 비율 | **30% 미만 권장** |
| **RSI** | Relative Strength Index | 과매수/과매도 지표 | 15분봉 50 이상 필수 |
| **MACD** | Moving Average Conv. Div. | 추세의 방향과 강도 측정 | 골든크로스 확인용 |

---

## 3. 매수 시그널 조건 (Entry Rules)

다음 모든 조건이 **동시에 만족(AND)**될 때 진입합니다.

### Step 1: 대세 확인 (15분봉)
- [ ] **RSI(15m)** > 50 (우상향 추세)
- [ ] **Price** > MA20(15m) (추세 유지)

### Step 2: 기회 포착 (5분/1분봉)
- [ ] **RVOL** > 2.0 (평소보다 2배 이상의 거래량 동반)
- [ ] **Price** > **VWAP** (세력의 단가보다 높은 위치)
- [ ] **MACD Histogram** > 0 (상승 모멘텀 지속)

### Step 3: 최종 필터 (Candle Shape)
- [ ] **Wick Ratio** < 30% (매도세보다 매수세가 압도적임)
- [ ] **Price** > 전일 고가 혹은 당일 시가 (주요 저항선 돌파)

---

## 4. 가짜 돌파 방지 및 위험 알림 (False Breakout Filter)

아무리 가격이 올라도 아래 조건에 해당하면 **'매수 금지'** 혹은 **'탈출'** 시그널을 보냅니다.

*   **위험 1 (Wick Trap)**: 거래량은 터졌으나 윗꼬리가 전체 캔들의 50% 이상일 때 (Pump & Dump 주의)
*   **위험 2 (VWAP Fade)**: 급등 후 주가가 VWAP 아래로 하향 돌파할 때 (세력이 털고 나간 신호)
*   **위험 3 (Divergence)**: 가격은 신고가를 경신하지만, 거래량이나 RSI는 낮아질 때 (힘의 소진)

---

## 5. 사례 분석: 드림랜드(TDIC)
*   **급등기 (5/12~13)**: 15분봉 RSI 70 돌파, RVOL 10배 이상, VWAP 위에서 안정적 흐름 유지.
*   **급락기**: 장중 윗꼬리 60% 이상 발생 및 VWAP 하향 돌파 시점이 최종 매도 타점.
