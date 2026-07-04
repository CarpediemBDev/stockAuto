# 📈 StockAuto 매매보고서(Trading Report) 기능 강화 및 업데이트 상세 계획서

본 문서는 StockAuto 시스템의 `/report` 메뉴를 실전 분석 중심의 트레이딩 대시보드로 고도화하기 위한 기능 설계 및 구현 로드맵을 정의합니다.

---

## 🎯 1. 개요 및 목적
* **현재 상태**: 체결 목록 리스트 및 기본적인 누적 수익금 표기 위주 제공.
* **업데이트 목적**: 전략별 승률/손익비 분석, 기간별 누적 수익률(Equity Curve) 차트 시각화, 매매 복기 일지 및 데이터 수출(Export) 기능을 통합하여 실전 자동매매 피드백 루프 완성.

---

## 💡 2. 주요 업데이트 핵심 기능 (Core Features)

### 📊 A. 계좌 누적 수익률 차트 (Equity Curve & MDD)
* **내용**: 일별/주별 계좌 평가액 변화 및 마이너스 낙폭(Drawdown)을 시각적 선/영역 차트로 표시.
* **지표**:
  * 누적 수익률 (%) / 누적 실현 손익 (KRW/USD)
  * MDD (Maximum Drawdown, 최대 낙폭)
  * Sharpe Ratio / Sortino Ratio (위험 조정 수익률)

### 🏆 B. 전략별 성과 비교 스코어카드 (Strategy Scorecard)
* **내용**: 각 매매 전략(변동성 돌파, 추세 추종, 스윙 등)별로 체결 건수 및 성과를 분리 집계.
* **지표**:
  * 총 매매 횟수 / 승률 (Win Rate %)
  * Profit Factor (총 이익 / 총 손실 비율)
  * 평균 익절률 vs 평균 손절률 (손익비)
  * 전략별 최고/최저 수익 종목 랭킹

### 📝 C. 매매 복기 노트 및 데이터 수출 (Trading Journal & Export)
* **내용**:
  * 각 체결(Trade)별 아이콘을 클릭하여 "매수 이유", "시장 상황 메모" 작성 및 저장.
  * 기간별/전략별 매매 내역을 Excel/CSV 파일로 원클릭 다운로드.

---

## 🛠️ 3. 기술 구현 아키텍처 및 API 계약 설계

### 🔌 백엔드 API (`backend/app/report/router.py`)
1. `GET /api/v1/report/analytics`
   * **Query Params**: `start_date`, `end_date`, `strategy_id`
   * **Response**: `{ equity_curve: [...], strategy_metrics: {...}, mdd: number, win_rate: number, profit_factor: number }`
2. `POST /api/v1/report/trades/{trade_id}/note`
   * **Request Body**: `{ note: string }`
3. `GET /api/v1/report/export`
   * **Query Params**: `format` (`csv` | `xlsx`) -> File Download Stream 반환.

### 🎨 프론트엔드 UI/UX (`frontend/app/report/page.tsx`)
* **차트 라이브러리**: `recharts` 활용 (`ResponsiveContainer`, `AreaChart`, `BarChart`).
* **탭 구조**:
  * `[ 📊 성과 대시보드 ]` | `[ 📋 상세 체결 이력 ]` | `[ 📑 전략별 분석 ]`

---

## 📅 4. 단계별 구현 일정
1. **Phase 1**: 백엔드 집계 유틸리티 및 `analytics` API 개발.
2. **Phase 2**: 프론트엔드 Equity Curve 및 전략 스코어카드 차트 연동.
3. **Phase 3**: 매매 복기 메모 및 CSV Export 엔드포인트 연동 및 회귀 테스트.
