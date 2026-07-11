# 📥 yfinance 시세 데이터 로컬 캐싱 및 한도 우회 아키텍처 (DATA_CACHING.md)

본 문서는 **StockAuto** 프로젝트에서 야후 파이낸스(yfinance) API의 IP 차단(429)을 방지하고 백테스팅 및 마켓 스캐너 연산을 초고속으로 수행하기 위해 설계된 **Parquet 로컬 영구 캐싱 엔진 및 API 한계 우회 정책**을 설명합니다.

---

## 1. 캐싱 엔진 아키텍처 (Cache Hit & Miss)

야후 파이낸스(yfinance)는 짧은 시간에 반복적으로 조회를 요청하면 즉각 IP 차단(HTTP 429 Too Many Requests)을 보냅니다. 이를 원천 차단하기 위해 **조회 파라미터를 식별자로 한 로컬 Snappy Parquet 캐싱 시스템**을 가동합니다.

### 🔄 데이터 조회 및 캐싱 프로세스

`mermaid
graph TD
    Start([백테스트/스캐너 데이터 요청]) --> BuildKey[1. 조회 파라미터 조합 빌드]
    BuildKey --> GenerateHash[2. SHA-1 해시 키 변환]
    GenerateHash --> CheckCache{3. backend/data/cache/<br>해시.parquet 파일 존재 여부}
    
    CheckCache -- 존재함 (Cache HIT) --> LoadLocal[4. 로컬 Parquet 파일 로드<br>0.1초 소요 / 네트워크 트래픽 0]
    CheckCache -- 존재하지 않음 (Cache MISS) --> yfinanceRequest[5. yfinance API 벌크 다운로드]
    
    yfinanceRequest --> CheckEmpty{6. 데이터 반환 여부}
    CheckEmpty -- 성공 --> SaveCache[7. 해당 해시 파일명으로<br>Parquet 압축 저장]
    SaveCache --> End([메모리 적재 및 백테스트 진행])
    LoadLocal --> End
    
    CheckEmpty -- Empty DataFrame / 429 차단 --> ErrorHandling[8. 안전 백오프 가동<br>청크 크기 20개 축소 및 5초 대기]
    ErrorHandling --> yfinanceRequest
`

---

## 2. 해시명(Cache Key)의 생성 기준

하드디스크의 ackend/data/cache/ 폴더 내에 저장되는 91c329cf...parquet 형태의 파일명은 아래 **5가지 파라미터 조합**을 SHA-1 알고리즘으로 해시화한 고유 식별자입니다.

`python
cache_key = (
    tuple(sorted(tickers_list)),  # 1. 정렬된 종목 리스트 조합
    interval,                      # 2. 인터벌 해상도 (1d, 1h, 15m)
    period,                        # 3. yfinance 기한 (옵션)
    str(start_date),               # 4. 조회 시작 날짜
    str(end_date)                  # 5. 조회 종료 날짜
)
`

> [!TIP]
> **데이터 불일치 방지**: 
> 종목 리스트가 단 하나만 달라지거나, 조회 시작/종료일이 하루라도 변경되면 해시 파일명이 아예 다르게 분기되므로 옛날 캐시와 섞이거나 엉뚱한 데이터를 불러오는 오작동이 원천 차단됩니다.

---

## 3. 야후 파이낸스(yfinance) API 인터벌별 물리적 한계

야후 파이낸스 서버가 제공하는 과거 데이터(Lookback) 보관 주기는 인터벌에 따라 엄격하게 제한되어 있으며, 이를 초과해 요청하면 **아무 에러 없이 빈 데이터프레임(Empty DataFrame)을 반환**합니다.

| 인터벌 (Interval) | 최대 지원 과거 기간 (Period Limit) | 특징 및 주의사항 |
| :---: | :---: | :--- |
| **1일봉 (1d)** | **무제한 (Unlimited)** | 수십 년 전 과거 기록까지 안전하게 조회 가능 |
| **1시간봉 (1h)** | **최대 최근 730일 (2년)** | 2년이 넘어가는 시나리오는 자동으로 1d(일봉)로 하향 매칭 필요 |
| **15분봉 (15m)** | **최대 최근 60일** | 1시간 미만의 모든 인트라데이(5m, 2m, 1m 등) 공통 한계 |
| **1분봉 (1m)** | **최대 최근 7일 ~ 30일** | 라이브러리 정책에 따라 7일 초과 시 ValueError 반환 |

---

## 4. QQQ 레짐 한도 클리핑 및 웜업 보정 공식

이동평균선(EMA20, EMA50) 등의 지표를 계산하기 위해서는 백테스트 시작일 이전에 미리 데이터를 받아 지표를 그리는 **웜업 기간(Warmup Days)**이 필수적입니다.
하지만 웜업 기간을 확보하기 위해 시작 날짜를 너무 과거로 밀면, 15분봉의 60일 한계선에 부딪혀 QQQ 지수 데이터를 전혀 받지 못하고 뻗어버리는 문제가 발생합니다.

### 🛠️ 실전 해결 코드 (datetime.now() 기준 동적 클리핑)

yfinance의 한도 검사 기준점은 백테스트 종료일(download_end)이 아니라 **프로그램을 실행하고 있는 현재 시간(오늘)**입니다. 따라서 동적으로 과거 한계를 역산하여 클리핑해야 합니다.

`python
# backend/app/bot/backtest_engine.py

# yfinance 한도는 언제나 '현재 호출하는 시점(오늘)' 기준이므로,
# download_end가 아닌 datetime.now() 기준으로 역산하고 2일의 안전 마진을 둡니다.
limit_days = {
    "1m": 27,
    "5m": 57,
    "15m": 57,
}.get(self.interval, None)

if limit_days is not None:
    max_allowed_start = datetime.now() - timedelta(days=limit_days)
    if download_start < max_allowed_start:
        logger.warning(
            f"[Backtest] Interval {self.interval} requested start date "
            f"{download_start.date()} exceeds yfinance limit. "
            f"Clipping to {max_allowed_start.date()}"
        )
        download_start = max_allowed_start
`

이 안전 마진 설계 덕분에, 오늘 실행하더라도 야후 파이낸스 한도 경계선에 걸치지 않고 QQQ 및 대상 종목의 모든 15분봉 정밀 데이터를 성공적으로 긁어와 캐시를 적재할 수 있습니다.
