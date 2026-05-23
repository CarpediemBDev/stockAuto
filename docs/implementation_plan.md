# 🛠️ StockAuto v2.0 시세 벤더 독립성 100% 최종 완성 계획서 (Phase 18)

본 계획서는 최근 `scanner.py`, `scheduler.py`, `router_market.py` 등 주요 모듈에서 `yfinance` 결합을 전면 해제한 것에 이어, 아직 시스템 변두리에 남아있던 `kis_api.py`와 `translator.py` 내부의 날것(Raw) `yfinance` 임포트 및 호출부를 완전히 도려내어 **`data_provider.py` 단 한 곳으로 시세 공급원을 100% 캡슐화**하기 위한 최종 정밀 설계도입니다.

---

## 1. 🚨 잔존하는 yfinance 강결합 진단

시스템 내에서 `yfinance` 또는 `yf.Ticker`를 직접 명시하여 호출하는 잔재 파일들을 전수 조사한 결과, 다음 2개 핵심 파일에 총 3군데의 직접 의존성이 남아 있음을 식별했습니다.

### ① `backend/app/bot/kis_api.py` (2군데)
1. **Line 106 (`get_account_balance`)**: 가상 모의투자(Simulated/Paper Trading) 평가 자산 연산을 위해 holdings 종목의 현재가를 조회할 때 `yf.download(tickers, ...)`를 직접 동기식으로 호출 중.
2. **Line 256 (`_get_exchange_code`)**: 티커의 실제 해외 거래소(NASD/NYSE/AMEX)를 동적으로 판별하기 위해 `yf.Ticker(ticker).fast_info`를 다이렉트로 호출 중.

### ② `backend/app/translations/translator.py` (1군데)
1. **Line 66 (`translate`)**: 로컬 DB에 아직 매핑 정보가 등록되지 않은 신규 미국 주식의 영문 사명을 알아내기 위해 `yf.Ticker(ticker_clean).info`를 직접 호출 후 구글 번역 OpenAPI와 연동(자가학습) 중.

---

## 2. 🛠️ 캡슐화 및 추상화 고도화 설계 (Proposed Changes)

이러한 강결합을 해제하기 위해, 모든 `yfinance` 연동을 `data_provider.py`가 관리하는 단일 추상 장벽 안으로 가두고 외부 파일은 오직 이 프로바이더 인터페이스만 호출하도록 설계합니다. 

특히, `kis_api.py`와 `translator.py` 내의 해당 지점들은 **동기(Synchronous) 함수 흐름** 속에서 호출되므로, 비동기 이벤트 루프 밖에서도 충돌 없이 안전하게 호출될 수 있는 **동기식 헬퍼 인터페이스**를 `data_provider.py`에 추가 공급합니다.

### ⚙️ [MODIFY] [data_provider.py](file:///d:/dev/workspace/stockAuto/backend/app/scanner/data_provider.py)
*   **[신규] `fetch_bulk_ohlcv_sync` 추가**: 동기 호출 부서(`get_account_balance`)용 동기식 벌크 다운로드 API 공급.
*   **[신규] `fetch_ticker_info_sync` 추가**: 동기 자가학습 부서(`translator.py`)용 동기식 종목 기본정보(info) API 공급.
*   **`fetch_ticker_fast_info` 유지**: 동기 거래소 판별 부서(`_get_exchange_code`)를 위해 기존 동기 API 호환성 엄격 보장.

```python
def fetch_bulk_ohlcv_sync(tickers: list, interval: str, period: str, group_by: str = "ticker") -> pd.DataFrame:
    """
    여러 종목의 OHLCV 데이터를 동기식으로 다운로드합니다. (동기 API/메서드용)
    """
    if not tickers:
        return pd.DataFrame()
    try:
        data = yf.download(
            tickers, 
            period=period, 
            interval=interval, 
            group_by=group_by, 
            progress=False
        )
        return data
    except Exception as e:
        print(f"[DataProvider] Error in sync bulk download for {len(tickers)} tickers ({interval}): {e}")
        return pd.DataFrame()

def fetch_ticker_info_sync(ticker: str) -> dict:
    """
    종목의 실시간 재무/기본정보(info)를 동기식으로 안전하게 수집합니다. (동기 API용)
    """
    try:
        ticker_obj = yf.Ticker(ticker)
        return ticker_obj.info if ticker_obj.info else {}
    except Exception as e:
        print(f"[DataProvider] Error fetching sync info for {ticker}: {e}")
        return {}
```

---

### ⚙️ [MODIFY] [kis_api.py](file:///d:/dev/workspace/stockAuto/backend/app/bot/kis_api.py)
*   파일 상단의 `import yfinance as yf` 및 인라인 임포트부를 **완전 박멸**.
*   `from app.scanner.data_provider import fetch_bulk_ohlcv_sync, fetch_ticker_fast_info` 임포트.
*   `yf.download` 호출부를 `fetch_bulk_ohlcv_sync` 호출로 교체.
*   `yf.Ticker(ticker).fast_info` 호출부를 `fetch_ticker_fast_info(ticker)` 호출로 교체.

---

### ⚙️ [MODIFY] [translator.py](file:///d:/dev/workspace/stockAuto/backend/app/translations/translator.py)
*   파일 내의 인라인 `import yfinance as yf` 완전 제거.
*   `from app.scanner.data_provider import fetch_ticker_info_sync` 임포트.
*   `yf.Ticker(ticker_clean).info` 호출부를 `fetch_ticker_info_sync(ticker_clean)` 호출로 교체.

---

## 3. 🧪 검증 계획 (Verification Plan)

### A. 정밀 구문 컴파일 검증
*   `py_compile`을 사용하여 정화된 `data_provider.py`, `kis_api.py`, `translator.py`의 구문 완성도를 100% 검증하여 빌드 완성도 사전 확보.

### B. 가상 및 실전 런타임 안정성 검사
1. **백엔드 기동 테스트**: Uvicorn 백엔드를 로컬로 기동하고, 초기 가상 잔고 계산 및 번역 사전 데이터 로드 시 터지는 에러가 없는지 콘솔 로그 추적.
2. **동적 벤더 격리 증명**: `data_provider.py` 내의 `yfinance` 호출부만 Mock 데이터를 반환하도록 조작했을 때, `kis_api.py`와 `translator.py`를 단 한 글자도 건드리지 않고 시스템이 모킹 데이터로 정상 구동되는지 테스트하여 결합 해제 완성도 증명.
