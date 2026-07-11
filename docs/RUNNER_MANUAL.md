# 🏃‍♂️ StockAuto 백테스트 및 수집 러너 스크립트 매뉴얼 (RUNNER_MANUAL.md)

본 문서는 StockAuto 프로젝트의 백엔드(ackend/) 디렉터리에 위치한 핵심 파이썬 스크립트들의 역할, 작동 흐름, 유기적인 연결 관계를 명확히 정의합니다.

---

## 1. 스크립트 요약 지도

| 스크립트명 | 핵심 역할 | 실행 주기 / 시점 | 출력 결과물 |
| :--- | :--- | :--- | :--- |
| **scratch_harvester.py** | 야후 파이낸스에서 대상 종목들의 데이터를 청크 단위로 분할 및 딜레이 가드를 적용해 수집 | 전략 배틀 기동 전 (1회 데이터 사전 확보용) | ackend/data/cache/*.parquet<br>cache_harvest_report.md |
| **un_tournament.py** | 단일 종목군, 특정 인터벌 및 날짜 범위를 대상으로 등록된 전략들의 CPU 병렬 백테스트를 돌려 우승전략 판별 | 필요시 단일 시나리오 정밀 분석 | 콘솔 로그 및 결과 JSON |
| **un_all_tournaments.py** | 30종 다차원 시나리오 루프를 돌며 un_tournament.py를 순차 호출해 1차 예선전을 완주하는 마스터 스케줄러 | 1차 대항전 개시 시 (전체 전략 검증) | docs/history/<br>strategy_tournament_report_V5.md |
| **un_championship.py** | 1차에서 선발된 최정예 전략 7종만 추려내어, 확장된 2,590개 종목 전체에 대입해 2차 챔피언십 배틀을 가동하는 스케줄러 | 2차 대항전 개시 시 (주도 전략 검증) | docs/history/<br>strategy_championship_report_V1.md |

---

## 2. 각 스크립트별 동작 원리 및 유기적 흐름

`mermaid
graph TD
    %% 1. Tickers 및 DB 준비
    TickersJson[도메인별 tickers.json] --> Harvester
    DBDynamic[DB 관심/보유/이력 종목 추출] --> Harvester[scratch_harvester.py]
    
    %% 2. 데이터 수집 단계
    Harvester -- yfinance 벌크 API 호출 --> LocalCache[(data/cache/ *.parquet)]
    
    %% 3. 1차 예선전 단계
    LocalCache --> RunAll[run_all_tournaments.py]
    RunAll -- 75+개 전체 전략 루프 --> RunTournament[run_tournament.py]
    RunTournament -- CPU ProcessPool 가동 --> TestResults[1차 30종 매치 결과]
    TestResults --> TournamentReport[strategy_tournament_report_V5.md]
    
    %% 4. 2차 본선 챔피언십 단계
    TournamentReport -- 우승 전략 7종 선별 --> RunChamp[run_championship.py]
    LocalCache --> RunChamp
    RunChamp -- 2,590개 확장 종목 대입 --> RunTournament
    RunTournament --> ChampReport[strategy_championship_report_V1.md]
`

### 1) scratch_harvester.py (시세 데이터 사전 수집기)
*   **작동 원리**: 야후 파이낸스 서버가 동시 다발적인 다운로드 요청을 받으면 IP 차단(429)을 거는 것에 대응합니다. 종목 리스트를 50개 단위 청크로 쪼개고, 청크당 0.5초~1.5초 사이의 난수 대기 시간을 강제로 주입하며 백그라운드 스레드 풀에서 안전하게 다운로드합니다.
*   **출력**: 받아온 시세 데이터는 Snappy 압축 알고리즘을 사용한 로컬 Parquet 파일로 직렬화되어 영구 저장됩니다.

### 2) un_tournament.py (백테스트 병렬 코어 엔진)
*   **작동 원리**: 지정된 티커 파일 전체를 로드하여 로컬 Parquet 캐시에 해당 데이터가 있는지 조회(Cache HIT)합니다. 데이터가 메모리에 적재되면, 파이썬의 멀티프로세싱 모듈(ProcessPoolExecutor)을 기동하여 컴퓨터의 CPU 코어 개수에 맞춰 여러 개의 전략 백테스트를 동시에 가동(Parallel Simulation)시킵니다.
*   **출력**: 각 전략별 최종 수익률, Sharpe 지수, MDD를 연산하여 종합 점수(Selection Score)를 매기고 순위를 정렬해 반환합니다.

### 3) un_all_tournaments.py (1차 30종 시나리오 마스터 스케줄러)
*   **작동 원리**: 5대 도메인(우량주, 잡주, 기술주, 중국주, 이탈리아주)에 대해 장기전(3년 일봉), 중기전(1년 시간봉), 단기전(60일 분봉) 등 30가지의 매치 시나리오 배열을 정의해 두고, un_tournament.py를 루프를 돌며 실행합니다.
*   **출력**: 30개 매치가 끝날 때마다 우승 전략을 취합하여 V5 종합 보고서를 작성합니다.

### 4) un_championship.py (2차 챔피언십 정예 러너)
*   **작동 원리**: 1차 예선전 결과를 기반으로 75개 전략 중 1위를 거머쥔 **7대 정예 전략**만 선출합니다. 이 정예 군단을 확장된 **2,590개 전수 종목**에 대입하여 30종 매치 루프를 다시 돌립니다.
*   **특징**: 전략 수가 대폭 축소되어 종목이 5배 이상 늘어났음에도 연산 속도가 극대화됩니다.

---

## 3. 물리적 데이터 규격 정보

*   **저장 포맷**: Snappy Compressed Columnar Parquet (.parquet)
*   **데이터 용량**: **총 2,590개 고유 종목** (3개 인터벌) 기준 **734.39 MB (총 432개 파일)**
*   **효율성**: 텍스트 포맷(CSV) 대비 용량을 약 80% 이상 절감하여 기가바이트 미만의 메모리 점유율로 초고속 I/O 연산이 가능합니다.
