---
name: mass-backtest-tournament
description: 500개 종목 5대 도메인(우량주, 잡주, 기술주, 중국주, 이탈리아주)에 대한 다차원(3년, 1년, 3개월) 병렬 백테스트 토너먼트를 5인의 하이브리드 에이전트 분업 및 CPU 멀티프로세싱 가속을 통해 25분 이내로 안전하게 실행하는 재사용 가능 워크플로우 스킬입니다.
---

# 🏆 StockAuto 대규모 다차원 백테스트 토너먼트 워크플로우 (SKILL.md)

본 문서는 **StockAuto** 전략들의 한계 성능과 강건성(Robustness)을 교차 검증하기 위해, **5대 종목군(각 100개, 총 500개)**에 대해 다양한 기간(3년, 1년, 3개월) 및 인터벌(1d, 1h, 15m/5m)에 걸쳐 대규모 병렬 백테스팅을 가속화하여 구동하고 분석하기 위한 재사용 가능한 공식 워크플로우 명세서입니다.

---

## 🧭 1. 하이브리드 5인 서브에이전트 배치 모델

토큰 리소스를 최적화하고 속도를 극대화하기 위해, 단순 작업은 **Flash** 모델의 분산 병렬 처리를 수행하고, 고난도 통계 분석 및 수치 검증은 **Pro** 모델의 중앙 집중형 종합 분석으로 구성합니다.

```
                           ┌──────────────────────┐
                           │    Antigravity       │
                           │   (Main Agent)       │
                           └──────────┬───────────┘
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            ▼                         ▼                         ▼
   [종목 발굴: Flash]       [시뮬레이션: Flash]       [분석/감사: Pro]
   5명의 Ticker Selector    Battle Commander          1명의 Robustness Analyst
   (분야별 100개 동시 선발)  (CPU 멀티코어 병렬 연산)  1명의 Critical Auditor
```

### 1) 종목 선발 및 정제원 (`ticker_selector` - 5명 병렬 Flash 기동)
* **임무**: 5대 종목군(우량, 잡주, 기술, 중국, 이탈리아)에 각각 1명씩 배치되어 로컬 `tickers.json`을 1차 자동 분류하고, 모자란 수량은 핀포인트 인터넷 검색을 통해 채워 **분야별 100개씩 총 500개 유효 티커 JSON**을 즉시 확보합니다.

### 2) 시세 데이터 수집원 (`data_harvester` - 1명 Flash 기동)
* **임무**: 500개 티커 리스트를 인계받아 yfinance API 429 차단을 우회하기 위한 배치 큐(Batch Queue, 50개 단위 묶음)와 임의 딜레이를 활용하여 3년 일봉, 1년 시간봉, 최근 60일 분봉 데이터를 로컬 캐시에 Parquet 포맷으로 압축 적재합니다.

### 3) 백테스트 구동원 (`battle_commander` - 1명 Flash 기동)
* **임무**: `ProcessPoolExecutor` 프로세스 풀을 열어 5개 종목군 x 3개 기간 x 2개 인터벌의 **총 30가지 조합 대항전을 CPU 멀티코어로 병렬 시뮬레이션**하여 10분 내로 연산을 완수합니다.

### 4) 강건성 통계 평가가 (`robustness_analyst` - 1명 Pro 기동)
* **임무**: 500개 종목의 전체 시뮬레이션 통합 결과 데이터를 건네받아, 각 장세별 PnL 편차, MDD, Sharpe 비율의 통계적 우위를 분석하여 시장 레짐에 오버피팅되지 않는 **최종 초강건 올라운더 우승 전략**을 감별합니다.

### 5) 품질 및 수치 감사관 (`critical_auditor` - 1명 Pro 기동)
* **임무**: 이탈리아/중국 주식 백테스팅 시 타임존 시차, FX 환율 효과, 수수료 및 슬리피지가 현실적으로 반영되었는지 감수하고, QQQ 단순 보유 성적 산출식의 누적 복리 계산 무결성을 검증합니다.

---

## ⚡ 초고속 시뮬레이션 가속화 아키텍처

본 워크플로우를 실행하는 개발자는 백백테스팅 엔진 구성 시 아래 3대 가속 기술을 필수로 적용해야 합니다.

### ① yfinance API 벌크 호출 (Bulk Batching)
* 1개씩 500번 요청하는 대신, **50개 종목을 공백으로 묶어 총 10회의 벌크 쿼리**로 요청하여 다운로드 소요 시간을 1.5시간에서 **5분 내외**로 절감합니다.
  ```python
  import yfinance as yf
  # 50개씩 청크 분할하여 다운로드
  df = yf.download("AAPL MSFT TSLA ...", group_by="ticker", start="2023-07-09", end="2026-07-09")
  ```

### ② concurrent.futures 멀티프로세싱 (CPU Multi-Processing)
* 싱글코어 루프 연산 대신 CPU 물리 코어 개수만큼 프로세스 풀을 할당하여 백테스팅 연산을 동시 수행합니다. 연산 시간을 1시간에서 **10분 내외**로 가속합니다.
  ```python
  from concurrent.futures import ProcessPoolExecutor
  with ProcessPoolExecutor(max_workers=num_cores) as executor:
      results = list(executor.map(run_single_backtest, backtest_tasks))
  ```

### ③ 칼럼나 Parquet 캐싱 (Parquet Caching)
* yfinance에서 받아온 시세는 CSV나 SQLite 대신 판다스 I/O가 최대 10배 이상 빠른 **Parquet 파일**로 디렉터리에 캐싱하여 파일 적재 오버헤드를 최소화합니다.

---

## ⚙️ 단계별 실행 및 기동 가이드

본 스킬에 의거해 백테스트를 실행할 때는 다음 순서로 진행합니다:

### 1단계: 티커 분류 및 선발 스크립트 실행
* `ticker_selector` 에이전트들이 도출한 JSON 파일들을 `backend/data/` 경로에 적재합니다:
  * `tickers_bluechip.json` (우량주)
  * `tickers_penny.json` (잡주)
  * `tickers_tech.json` (기술주)
  * `tickers_china.json` (중국주)
  * `tickers_italy.json` (이탈리아주)

### 2단계: run_tournament.py 리팩토링 검증
* CLI 인자와 `ProcessPoolExecutor`가 가동되는지 확인 후 문법 무결성 검증을 수행합니다.
  ```bash
  python -m py_compile backend/run_tournament.py
  ```

### 3단계: 도메인 및 기간별 배틀 기동 (CLI Quick Commands)
* **3개년 장기전 (일봉, 1d)**
  ```bash
  python run_tournament.py --tickers_file backend/data/tickers_bluechip.json --start 2023-07-09 --end 2026-07-09 --interval 1d
  ```
* **1개년 중기전 (시간봉, 1h)**
  ```bash
  python run_tournament.py --tickers_file backend/data/tickers_tech.json --start 2025-07-09 --end 2026-07-09 --interval 1h
  ```
* **최근 60일 단기 초민감도전 (분봉, 15m/5m)**
  ```bash
  python run_tournament.py --tickers_file backend/data/tickers_penny.json --start 2026-05-09 --end 2026-07-09 --interval 15m
  ```

### 4단계: 교차 분석 및 정밀 감사
* 시뮬레이션 연산이 종료되면 `robustness_analyst`와 `critical_auditor`를 기동하여 최종 분석 및 검수 보고서를 도출하고, 이를 바탕으로 백테스트 아레나에 최종 우승 리더보드를 기록합니다.
