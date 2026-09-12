# -*- coding: utf-8 -*-
"""손절·트레일링 ATR 시간 프레임 비교 실행기.

## 무엇을 실증하는가

`app/scanner/scanner.py`는 ATR을 **5분봉**(`calculate_atr(df_5m, period=14)`)으로 계산하는데,
그 값을 소비하는 `get_stop_loss_pct` / `get_trailing_stop_pct` / `get_harvest_*_pct`는 전부
**일 단위 손절 폭**을 산정한다. 시간 프레임이 어긋나 ATR%가 하한을 넘지 못한다.

측정치(2026-09-10, 5일치 3,397개 5분봉, 10종목): 5분봉 ATR% 중앙값 0.19%.
하한을 넘으려면 2.00%가 필요하다. 대형주·ETF는 단 한 봉도 넘지 못했고, 초변동성
페니주에서만 가끔 넘는다. 즉 네 임계는 사실상 상수 3.0 / 2.0 / 5.0 / 15.0으로 동작한다.

이 스크립트는 "일봉 ATR로 바꾸면 나아지는가"를 봇의 실제 매수 이력으로 비교한다.

## 실행 전에 반드시 읽을 것

**자동으로 돌지 않는다. 사람이 명시적으로 실행해야 한다.**
scripts/evaluate_peak_detectors.py와 같은 이유다.

  1. yfinance 호출이 종목 수만큼 나간다. 라이브 스캐너가 같은 쿼터를 쓰므로 장중에 돌리면
     스캐너가 rate limit에 걸려 매매 사이클이 시그널 없이 돈다. **장 마감 후에 돌린다.**
  2. 결과는 라이브에 자동 반영되지 않는다. 손절 폭 변경은 라이브 A/B 계정의 매매 성격을
     통째로 바꾸므로, 이 표를 보고 사람이 결정한다.

사용법:

    cd backend
    venv/Scripts/python.exe scripts/evaluate_atr_timeframe.py --limit 30      # 스모크
    venv/Scripts/python.exe scripts/evaluate_atr_timeframe.py                 # 전체

## 비교 대상

  A. 현행  - 5분봉 ATR. 실측상 상시 하한이므로 손절 3.0% / 트레일링 2.0% 고정으로 모델링한다.
            (5분봉 데이터는 yfinance가 최근 60일만 주므로 90일 표본에 소급할 수 없다.
             하한 고정 모델링은 위 측정치에 근거한 근사이며, 이 근사가 이 비교의 전제다.)
  B. 일봉  - 진입 시점까지의 일봉 ATR14로 max(3.0, ATR%x1.5) / max(2.0, ATR%x1.0)

## 결과를 어떻게 읽는가

**원시 수익률이 아니라 A 대비 개선분으로 읽는다.** docs/strategy_alpha_verdict.md의 교훈이다.
급등주가 섞인 표본에서는 어떤 정책이든 큰 양의 수익이 나오므로 절대 숫자는 착시다.
개선분의 **중앙값**과 **표본 수**를 함께 본다. 평균은 밈주 아웃라이어 하나에 끌려간다.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.scanner.indicators import calculate_atr  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stockauto.db")

STOP_BASE, STOP_MULT = 3.0, 1.5      # base_strategy.get_stop_loss_pct
TRAIL_BASE, TRAIL_MULT = 2.0, 1.0    # base_strategy.get_trailing_stop_pct
HORIZON_BARS = 30                    # 진입 후 최대 보유 일수
CHUNK = 50                           # 앱의 fetch_bulk_ohlcv_sync와 같은 청크 크기


def load_entries(after: str, limit: int | None) -> list[tuple[str, str, float]]:
    """봇의 실제 매수 이력을 (티커, 진입일, 진입가)로 뽑는다.

    같은 티커·같은 날의 중복 매수(피라미딩)는 하나로 접는다. 한 진입을 여러 번 세면
    그 종목의 결과가 표본을 지배한다.
    """
    con = sqlite3.connect(DB)
    try:
        rows = con.execute(
            "SELECT ticker, substr(executed_at, 1, 10) AS d, AVG(price) "
            "FROM trade_logs WHERE trade_type = 'BUY' AND executed_at >= ? "
            "AND price > 0 GROUP BY ticker, d ORDER BY d",
            (after,),
        ).fetchall()
    finally:
        con.close()
    if not limit or len(rows) <= limit:
        return rows
    # 앞에서 자르면 표본이 가장 오래된 며칠에 몰린다. 기간 전체에서 고르게 뽑아야
    # 특정 장세(그 며칠의 레짐)의 결과를 전체로 오인하지 않는다. 시드를 고정해 재현 가능하게 둔다.
    import random

    return sorted(random.Random(20260910).sample(rows, limit), key=lambda r: r[1])


def download_daily(tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """일봉을 청크로 나눠 받는다. 종목당 개별 호출보다 쿼터 부담이 훨씬 작다."""
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), CHUNK):
        chunk = tickers[i:i + CHUNK]
        print(f"  [{i // CHUNK + 1}/{(len(tickers) + CHUNK - 1) // CHUNK}] {len(chunk)}종목 다운로드...")
        try:
            raw = yf.download(chunk, start=start, end=end, interval="1d",
                              auto_adjust=False, progress=False, group_by="ticker",
                              threads=False)
        except Exception as exc:
            print(f"    실패: {exc}")
            continue
        for t in chunk:
            try:
                df = raw[t] if len(chunk) > 1 else raw
                df = df.dropna(subset=["Close"])
                if len(df) > 20:
                    out[t] = df
            except (KeyError, TypeError):
                continue
    return out


def simulate(df: pd.DataFrame, entry_idx: int, entry_px: float,
             stop_pct: float, trail_pct: float) -> float | None:
    """진입 다음 봉부터 청산까지의 수익률(%)을 돌려준다.

    손절과 트레일링을 같은 봉에서 함께 보되, 손절을 먼저 판정한다. 일봉으로는 장중
    선후를 알 수 없으므로 보수적인 쪽(손실 확정)을 택한다. 이 근사는 두 정책에 동일하게
    적용되므로 비교에는 영향을 주지 않는다.
    """
    peak = entry_px
    end = min(entry_idx + 1 + HORIZON_BARS, len(df))
    for i in range(entry_idx + 1, end):
        low = float(df["Low"].iloc[i])
        close = float(df["Close"].iloc[i])
        stop_price = entry_px * (1 - stop_pct / 100)
        if low <= stop_price:
            return (stop_price - entry_px) / entry_px * 100
        if peak > entry_px:
            trail_price = peak * (1 - trail_pct / 100)
            if low <= trail_price:
                return (trail_price - entry_px) / entry_px * 100
        peak = max(peak, close)
    if end - 1 <= entry_idx:
        return None
    return (float(df["Close"].iloc[end - 1]) - entry_px) / entry_px * 100


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", default=(datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"))
    ap.add_argument("--limit", type=int, default=None, help="표본 상한 (스모크용)")
    args = ap.parse_args()

    entries = load_entries(args.after, args.limit)
    tickers = sorted({t for t, _, _ in entries})
    print(f"표본: 진입 {len(entries)}건 / 고유 {len(tickers)}종목 / {args.after} 이후\n")

    start = (datetime.strptime(args.after, "%Y-%m-%d") - timedelta(days=40)).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    data = download_daily(tickers, start, end)
    print(f"\n일봉 확보: {len(data)}/{len(tickers)}종목\n")

    results = []
    atr_pcts = []
    for ticker, day, entry_px in entries:
        df = data.get(ticker)
        if df is None:
            continue
        idx = df.index.searchsorted(pd.Timestamp(day, tz=df.index.tz))
        if idx <= 20 or idx >= len(df) - 2:
            continue
        hist = df.iloc[:idx + 1]
        atr_series = calculate_atr(hist, 14)
        if atr_series.empty:
            continue
        atr_pct = float(atr_series.iloc[-1]) / entry_px * 100
        if not (0 < atr_pct < 200):
            continue
        atr_pcts.append(atr_pct)

        a = simulate(df, idx, entry_px, STOP_BASE, TRAIL_BASE)                       # 현행(하한 고정)
        b = simulate(df, idx, entry_px,
                     max(STOP_BASE, atr_pct * STOP_MULT),
                     max(TRAIL_BASE, atr_pct * TRAIL_MULT))                          # 일봉 ATR
        if a is None or b is None:
            continue
        results.append((ticker, day, atr_pct, a, b))

    if not results:
        print("표본 없음 - 데이터 확보 실패")
        return

    rd = pd.DataFrame(results, columns=["ticker", "day", "atr_pct", "A_current", "B_daily"])
    rd["diff"] = rd["B_daily"] - rd["A_current"]

    ap_s = pd.Series(atr_pcts)
    print("=" * 74)
    print(f"일봉 ATR% 분포: 중앙값 {ap_s.median():.2f}%  (25% {ap_s.quantile(.25):.2f} / 75% {ap_s.quantile(.75):.2f})")
    wide = (ap_s * STOP_MULT > STOP_BASE).mean() * 100
    print(f"일봉 기준 손절이 하한(3.0%)을 넘는 비율: {wide:.1f}%   ← 5분봉에서는 사실상 0%")
    print("=" * 74)
    print(f"\n{'':16}{'중앙값':>10}{'평균':>10}{'승률':>10}")
    for col, label in [("A_current", "A 현행(고정)"), ("B_daily", "B 일봉ATR")]:
        print(f"{label:<16}{rd[col].median():>9.2f}%{rd[col].mean():>9.2f}%"
              f"{(rd[col] > 0).mean() * 100:>9.1f}%")
    print(f"\n{'개선분 (B-A)':<16}{rd['diff'].median():>9.2f}%{rd['diff'].mean():>9.2f}%"
          f"{(rd['diff'] > 0).mean() * 100:>9.1f}%")
    print(f"\n표본 {len(rd)}건 / {rd['ticker'].nunique()}종목")
    print(f"두 정책이 동일한 결과를 낸 비율: {(rd['diff'].abs() < 1e-9).mean() * 100:.1f}%")
    print("\n판독: 개선분 중앙값이 0 근처면 시간 프레임 교체의 실익이 없다는 뜻이다.")
    print("      절대 수익률(A/B 각 행)은 급등주 표본 때문에 부풀려 보이므로 근거로 쓰지 않는다.")


if __name__ == "__main__":
    main()
