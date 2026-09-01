"""매크로 시계열 수집 (FRED).

`macro_momentum` 전략이 읽는 `yield_curve_spread`와 `inflation_expectation`의 단일
공급 지점이다. 두 값이 없으면 `BaseStrategy._safe_get`이 기본값(0.1, 2.0)을 돌려주고,
그 기본값으로 계산한 `is_recession_alert`가 **항상 False**로 굳는다. 즉 전략 이름은
매크로 모멘텀인데 실제로는 금리도 물가도 판단에 개입하지 않는 EMA 추세 전략이 된다
(2026-09-01 실측).

FRED의 CSV 다운로드 엔드포인트는 **API 키가 필요 없다.** 일 단위 시계열이라 스캔
주기(10분)마다 받을 이유가 없어 캐시 TTL을 길게 둔다.

수집 실패 시 예외를 올리지 않고 None을 돌려준다. 값을 싣지 않으면 전략이 진입하지
않을 뿐이고, 이는 잘못된 값으로 매매하는 것보다 안전하다. 이 원칙은
`signal_contract.daily_indicator_snapshot`과 같다.
"""

import time
import threading

import pandas as pd
import requests

from app.core.logging import logger

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# 수집 대상 시리즈. 값의 의미가 바뀌면 백테스트 성적이 소급 변경되므로 교체 금지.
SERIES_TWO_YEAR = "DGS2"        # 2년 만기 국채 수익률 (%)
SERIES_TEN_YEAR = "DGS10"       # 10년 만기 국채 수익률 (%)
SERIES_BREAKEVEN = "T10YIE"     # 10년 기대인플레이션 (%)

MACRO_SERIES = (SERIES_TWO_YEAR, SERIES_TEN_YEAR, SERIES_BREAKEVEN)

# 일 단위 갱신 시리즈다. 6시간이면 장중에 한두 번만 받는다.
MACRO_CACHE_TTL_SECONDS = 6 * 60 * 60
_REQUEST_TIMEOUT_SECONDS = 5

# 실패도 캐시한다. 이 함수는 종목마다 호출되므로 실패를 기억하지 않으면
# 후보 수만큼 재시도해 스캔 한 사이클이 통째로 멈춘다(100종목 x 3시리즈 x 타임아웃).
MACRO_FAILURE_TTL_SECONDS = 10 * 60

_cache_lock = threading.Lock()
_macro_cache = {}  # key -> (timestamp, DataFrame)


def _remember_failure(cache_key: str) -> None:
    """수집 실패를 짧게 기억해 호출자마다 재시도하지 않게 한다."""
    with _cache_lock:
        _macro_cache[cache_key] = (time.time(), None)


def _fetch_series(series_id: str) -> pd.Series | None:
    """FRED에서 시리즈 하나를 받아 날짜 인덱스 시리즈로 만든다."""
    try:
        response = requests.get(
            FRED_CSV_URL,
            params={"id": series_id},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            logger.warning(
                "[MacroData] FRED %s 응답 코드 %s", series_id, response.status_code
            )
            return None

        from io import StringIO

        frame = pd.read_csv(StringIO(response.text))
        if frame.empty or frame.shape[1] < 2:
            return None

        # 첫 열이 날짜, 둘째 열이 값이다. 열 이름은 시리즈마다 다르므로 위치로 읽는다.
        dates = pd.to_datetime(frame.iloc[:, 0], errors="coerce")
        # 휴일·결측은 "."으로 온다. 숫자로 강제 변환하면 NaN이 된다.
        values = pd.to_numeric(frame.iloc[:, 1], errors="coerce")
        series = pd.Series(values.values, index=dates, name=series_id)
        series = series[series.index.notna()].dropna()
        return series if not series.empty else None
    except Exception:
        logger.exception("[MacroData] FRED %s 수집 실패", series_id)
        return None


def fetch_macro_series(force_refresh: bool = False):
    """매크로 시리즈 3종을 한 프레임으로 받아 돌려준다.

    반환 프레임의 열은 DGS2·DGS10·T10YIE이고 인덱스는 날짜다. 하나라도 받지 못하면
    None을 돌려준다 - 일부만 있는 상태로 스프레드를 계산하면 조용히 틀린 값이 된다.
    """
    cache_key = "macro"
    if not force_refresh:
        with _cache_lock:
            cached = _macro_cache.get(cache_key)
            if cached:
                age = time.time() - cached[0]
                frame = cached[1]
                if frame is None:
                    if age < MACRO_FAILURE_TTL_SECONDS:
                        return None
                elif age < MACRO_CACHE_TTL_SECONDS:
                    return frame.copy()

    collected = {}
    for series_id in MACRO_SERIES:
        series = _fetch_series(series_id)
        if series is None:
            logger.warning("[MacroData] %s 결손으로 매크로 스냅샷을 건너뛴다", series_id)
            _remember_failure(cache_key)
            return None
        collected[series_id] = series

    frame = pd.DataFrame(collected).sort_index()
    # 시리즈마다 발표일이 달라 결측이 생긴다. 직전 값으로 채우되 앞쪽 결측은 버린다.
    frame = frame.ffill().dropna()
    if frame.empty:
        _remember_failure(cache_key)
        return None

    with _cache_lock:
        _macro_cache[cache_key] = (time.time(), frame.copy())
    return frame


def macro_snapshot(macro_frame) -> dict:
    """매크로 프레임의 마지막 값에서 전략이 읽는 두 필드를 만든다.

    `yield_curve_spread`는 10년물에서 2년물을 뺀 값(%p)이다. 음수면 금리 역전이고,
    0에 가까우면 역전 직후 정상화 구간이다. `macro_momentum`이 이 두 국면을
    기대인플레이션과 함께 침체 경보로 쓴다.
    """
    if macro_frame is None or macro_frame.empty:
        return {}
    last = macro_frame.iloc[-1]
    try:
        return {
            "yield_curve_spread": float(last[SERIES_TEN_YEAR] - last[SERIES_TWO_YEAR]),
            "inflation_expectation": float(last[SERIES_BREAKEVEN]),
        }
    except (KeyError, TypeError, ValueError):
        return {}


def macro_columns_for_index(macro_frame, index) -> dict:
    """백테스트용. 주어진 봉 인덱스에 맞춘 매크로 열 두 개를 돌려준다.

    발표일이 거래일과 어긋나므로 직전 값으로 채운다(ffill). 라이브 스냅샷과 같은
    계산식을 써야 두 경로의 값이 같은 뜻을 갖는다.
    """
    if macro_frame is None or macro_frame.empty or index is None or len(index) == 0:
        return {}
    try:
        normalized = macro_frame.copy()
        normalized.index = pd.to_datetime(normalized.index).tz_localize(None)
        target = pd.to_datetime(pd.Index(index))
        if getattr(target, "tz", None) is not None:
            target = target.tz_localize(None)
        aligned = normalized.reindex(normalized.index.union(target)).ffill().reindex(target)
        spread = aligned[SERIES_TEN_YEAR] - aligned[SERIES_TWO_YEAR]
        breakeven = aligned[SERIES_BREAKEVEN]
        if spread.isna().all() or breakeven.isna().all():
            return {}
        return {
            "yield_curve_spread": spread.values,
            "inflation_expectation": breakeven.values,
        }
    except Exception:
        logger.exception("[MacroData] 매크로 열 정렬 실패")
        return {}
