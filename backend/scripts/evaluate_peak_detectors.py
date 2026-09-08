"""고점 판단 방법론 비교 실행기.

docs/plans/holding_management_modes.md 6절의 백로그를 실증하는 스크립트다. 판정기 구현과
비교 지표는 app/bot/peak_detectors.py가 소유하고, 여기서는 표본을 뽑아 돌리고 표를 찍는
일만 한다.

## 실행 전에 반드시 읽을 것

**이 스크립트는 자동으로 돌지 않는다. 사람이 명시적으로 실행해야 한다.**

두 가지 이유가 있다.

  1. yfinance 호출이 종목 수만큼 나간다. 라이브 스캐너가 같은 API 쿼터를 쓰므로, 장중에
     돌리면 스캐너가 rate limit에 걸려 매매 사이클이 시그널 없이 돌 수 있다.
     **장 마감 후에 돌린다.**
  2. 결과는 라이브에 자동 반영되지 않는다. 수확 모드는 되돌릴 수 없는 매도를 내므로,
     판정기 교체는 이 표를 보고 사람이 결정한다.

사용법:

    cd backend
    venv/Scripts/python.exe scripts/evaluate_peak_detectors.py --tickers HCTI,ATNF,BBIG
    venv/Scripts/python.exe scripts/evaluate_peak_detectors.py --tickers-file tickers_surge.txt

## 표본을 어떻게 고르는가

수확 모드가 실제로 겪는 상황만 표본이 되어야 한다. 즉 **반토막 난 뒤 급등한 구간**이다.
평범한 상승장 표본을 섞으면 어떤 판정기든 좋아 보이고 비교가 무의미해진다.

에피소드 정의:
  - 관측 시작가 대비 ARM_PCT 이상 올라간 시점부터 시작 (수확 모드의 무장 조건과 동일)
  - 그 뒤 MAX_EPISODE_BARS 봉까지를 한 에피소드로 자른다

## 결과를 어떻게 읽는가

**원시 청산가가 아니라 베이스라인 대비 개선분으로 읽는다.** docs/strategy_alpha_verdict.md의
교훈 그대로다. 급등주 표본에서는 어떤 판정기든 큰 양의 수익을 내므로 절대 숫자만 보면
전부 훌륭해 보인다. 그 착시로 76종 전략을 2,590종까지 늘려 놓고도 알파가 없었다.

개선분의 **중앙값**과 **표본 수**를 함께 본다. 평균은 밈주 아웃라이어 하나에 끌려간다.
표본이 20개 미만이면 어떤 차이도 결론으로 삼지 않는다.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.bot.peak_detectors import Bar, compare, default_detectors  # noqa: E402

# 무장 임계. 수확 모드의 하한(HARVEST_ARM_BASE_PCT)과 같은 값을 쓴다 - 평가 조건이
# 라이브 조건과 달라지면 이 표는 라이브에 대해 아무 말도 하지 못한다.
ARM_PCT = 15.0
MAX_EPISODE_BARS = 200
MIN_EPISODE_BARS = 40
MIN_SAMPLES_FOR_VERDICT = 20


async def _load_bars(ticker: str) -> list[Bar]:
    """일봉을 받아 Bar 목록으로 바꾼다.

    ATR은 여기서 한 번만 계산해 모든 판정기에 같은 값을 넘긴다. 판정기 안에서 각자
    계산하면 산출식이 갈려 비교가 오염된다.
    """
    from app.scanner.data_provider import fetch_ohlcv

    frame = await fetch_ohlcv(ticker, interval="1d", period="2y")
    if frame is None or frame.empty:
        return []

    bars: list[Bar] = []
    prev_close = None
    true_ranges: list[float] = []
    for _, row in frame.iterrows():
        high = float(row["High"])
        low = float(row["Low"])
        close = float(row["Close"])
        volume = float(row.get("Volume", 0.0) or 0.0)

        # 표준 True Range. 갭을 포함해야 급등주의 실제 변동폭이 잡힌다.
        true_range = high - low
        if prev_close is not None:
            true_range = max(true_range, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(true_range)
        atr = statistics.fmean(true_ranges[-14:]) if len(true_ranges) >= 14 else 0.0

        bars.append(Bar(high=high, low=low, close=close, volume=volume, atr=atr))
        prev_close = close
    return bars


def _extract_episodes(bars: list[Bar]) -> list[list[Bar]]:
    """무장 조건을 만족한 급등 구간만 잘라낸다.

    한 종목에서 여러 에피소드가 나올 수 있으나 겹치지 않게 자른다. 겹치면 같은 급등이
    표본에 두 번 들어가 그 종목의 가중치만 커진다.
    """
    episodes: list[list[Bar]] = []
    index = 0
    while index < len(bars):
        base = bars[index].close
        if base <= 0:
            index += 1
            continue
        armed_at = None
        for offset in range(index + 1, len(bars)):
            gain_pct = (bars[offset].high - base) / base * 100.0
            if gain_pct >= ARM_PCT:
                armed_at = offset
                break
        if armed_at is None:
            break
        episode = bars[armed_at: armed_at + MAX_EPISODE_BARS]
        if len(episode) >= MIN_EPISODE_BARS:
            episodes.append(episode)
        index = armed_at + len(episode)
    return episodes


async def _run(tickers: list[str]) -> int:
    improvements: dict[str, list[float]] = {}
    captures: dict[str, list[float]] = {}
    episode_count = 0

    for ticker in tickers:
        try:
            bars = await _load_bars(ticker)
        except Exception as exc:  # noqa: BLE001
            print(f"  [skip] {ticker}: {exc}")
            continue
        if not bars:
            print(f"  [skip] {ticker}: 데이터 없음")
            continue

        for episode in _extract_episodes(bars):
            table = compare(default_detectors(), episode)
            if not table:
                continue
            episode_count += 1
            for name, row in table.items():
                improvements.setdefault(name, []).append(
                    float(row["improvement_pct_vs_baseline"])
                )
                captures.setdefault(name, []).append(float(row["capture_rate"]))
        print(f"  [ok] {ticker}: 누적 에피소드 {episode_count}건")

    if not improvements:
        print("\n표본이 없다. 티커 목록이나 기간을 넓혀라.")
        return 1

    print(f"\n총 에피소드 {episode_count}건")
    print(f"{'판정기':<26}{'개선분 중앙값':>14}{'고점 대비 회수 중앙값':>22}")
    print("-" * 62)
    rows = sorted(
        improvements.items(), key=lambda item: statistics.median(item[1]), reverse=True
    )
    for name, values in rows:
        print(
            f"{name:<26}{statistics.median(values):>13.2f}%"
            f"{statistics.median(captures[name]) * 100:>21.1f}%"
        )

    if episode_count < MIN_SAMPLES_FOR_VERDICT:
        print(
            f"\n⚠️ 표본이 {episode_count}건뿐이다({MIN_SAMPLES_FOR_VERDICT}건 미만). "
            "어떤 차이도 결론으로 삼지 마라."
        )
    print(
        "\n판단은 개선분으로만 한다. 회수율이 높아 보여도 베이스라인보다 나아지지 않았다면 "
        "그것은 표본이 급등주라서 그런 것이다(docs/strategy_alpha_verdict.md)."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", help="쉼표로 구분한 티커 목록")
    parser.add_argument("--tickers-file", help="줄바꿈으로 구분한 티커 파일")
    args = parser.parse_args()

    tickers: list[str] = []
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.tickers_file:
        with open(args.tickers_file, encoding="utf-8") as handle:
            tickers = [line.strip().upper() for line in handle if line.strip()]

    if not tickers:
        parser.error("--tickers 또는 --tickers-file 중 하나가 필요하다")

    print(
        "⚠️ yfinance 호출이 종목 수만큼 나간다. 라이브 스캐너와 쿼터를 공유하므로 "
        "장 마감 후에 돌려라.\n"
    )
    return asyncio.run(_run(tickers))


if __name__ == "__main__":
    raise SystemExit(main())
