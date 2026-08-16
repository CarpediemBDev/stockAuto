"""지수 레버리지 레짐(자율 슬롯) 장기 일봉 백테스트 러너.

제품 백테스트 엔진(BacktestSimulator)의 '자율 슬롯 경로'를 그대로 호출한다(엔진 밖 재구현 금지).
같은 데이터축·같은 수수료 위에서 다음을 나란히 돌려 QQQ 총수익 초과 여부를 정직하게 판정한다:

  - leveraged_regime   : QQQ 200일 SMA(3일 확정) 위면 QLD(2x) 보유, 아래면 현금
  - benchmark_qqq_hold : QQQ 단순보유(공정 비교 기준선)
  - leveraged_regime_3x: (옵션) TQQQ(3x) — 생존편향(2010~ 상장)으로 수치 과대 주의

핵심 한계(감사관): 초과수익의 정체는 레버리지(베타)이지 종목선택 알파가 아니다. 레짐 필터의
실제 기여는 '수익 증대'가 아니라 'MDD 절단(리스크 관리)'이다. 판정은 이 관점으로 읽어야 한다.

실행 예:
  cd backend && venv/Scripts/python.exe ../scripts/run_leverage_backtest.py --start-date 2006-06-21
"""
import argparse
import asyncio
import os
import sys
from datetime import date

# 루트/백엔드 경로 추가 (엔진 임포트용)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.backtests.backtest_engine import BacktestSimulator  # noqa: E402


# (strategy_type, 자산 티커, 표시명)
_CONFIGS = [
    ("leveraged_regime", "QLD", "레짐 QLD 2x (SMA200·3일확정)"),
    ("benchmark_qqq_hold", "QQQ", "QQQ 단순보유 벤치마크"),
]
_AGGRESSIVE = ("leveraged_regime_3x", "TQQQ", "레짐 TQQQ 3x (공격형)")


async def _run_one(strategy_type: str, asset: str, start_date: str, end_date: str, initial_cash: float) -> dict:
    sim = BacktestSimulator(
        tickers=[asset],
        start_date=start_date,
        end_date=end_date,
        interval="1d",  # 자율 상태기계는 일봉 정의 — 엔진이 다른 인터벌을 거부한다
        initial_cash=initial_cash,
        strategy_type=strategy_type,
    )
    await sim.prepare_data()
    return sim.run()


async def run_leverage_backtest(start_date: str, end_date: str, initial_cash: float = 10000.0,
                                include_3x: bool = False) -> list[dict]:
    configs = list(_CONFIGS)
    if include_3x:
        configs.append(_AGGRESSIVE)

    results = []
    for strategy_type, asset, label in configs:
        report = await _run_one(strategy_type, asset, start_date, end_date, initial_cash)
        report["_strategy_type"] = strategy_type
        report["_asset"] = asset
        report["_label"] = label
        results.append(report)
    return results


def _fmt(report: dict) -> str:
    return (
        f"{report['_label']:32s} | "
        f"총수익 {report.get('total_return_rate', 0.0):+9.2f}% | "
        f"CAGR {report.get('annualized_return', 0.0):+7.2f}% | "
        f"MDD {report.get('mdd', 0.0):7.2f}% | "
        f"Calmar {report.get('calmar_ratio', 0.0):5.2f} | "
        f"Sharpe {report.get('sharpe_ratio', 0.0):5.2f} | "
        f"거래 {report.get('total_trades', 0):4d}회"
    )


def main():
    parser = argparse.ArgumentParser(description="지수 레버리지 레짐 자율 슬롯 장기 일봉 백테스트")
    parser.add_argument("--start-date", type=str, default="2006-06-21",
                        help="시작일 YYYY-MM-DD (기본 2006-06-21 = QLD 상장 초기)")
    parser.add_argument("--end-date", type=str, default=date.today().isoformat(),
                        help="종료일 YYYY-MM-DD (기본 오늘)")
    parser.add_argument("--initial-cash", type=float, default=10000.0, help="초기 예수금 (USD)")
    parser.add_argument("--include-3x", action="store_true", help="TQQQ 3x 공격형 포함(생존편향 주의)")
    args = parser.parse_args()

    print("=" * 96)
    print(f"🏛️ [StockAuto] 지수 레버리지 레짐 자율 슬롯 백테스트  ({args.start_date} ~ {args.end_date})")
    print("   엔진: BacktestSimulator 자율 경로 | 일봉 | 신호 익일 체결(룩어헤드 차단) | 수수료 SIMULATED_FEE_RATE")
    print("=" * 96)

    results = asyncio.run(run_leverage_backtest(
        args.start_date, args.end_date, args.initial_cash, include_3x=args.include_3x,
    ))

    for report in results:
        if "error" in report:
            print(f"{report.get('_label', '?'):32s} | 오류: {report['error']}")
            continue
        print(_fmt(report))

    # 판정: leveraged_regime vs benchmark_qqq_hold (같은 축·같은 수수료)
    regime = next((r for r in results if r["_strategy_type"] == "leveraged_regime" and "error" not in r), None)
    bench = next((r for r in results if r["_strategy_type"] == "benchmark_qqq_hold" and "error" not in r), None)
    print("-" * 96)
    if regime and bench:
        excess = regime["total_return_rate"] - bench["total_return_rate"]
        mdd_delta = bench["mdd"] - regime["mdd"]  # 음수(더 깊음) vs 양수(더 얕음)
        print(f"📈 QQQ 벤치마크(엔진 내부): {regime.get('qqq_bench_return_rate', 0.0):+.2f}%")
        if excess > 0:
            print(f"✅ 레짐이 QQQ 단순보유를 총수익 {excess:+.2f}%p 초과.")
        else:
            print(f"❌ 레짐이 QQQ 단순보유를 이기지 못함 (초과 {excess:+.2f}%p).")
        print(f"   MDD 차이(벤치−레짐): {mdd_delta:+.2f}%p  (양수면 레짐이 낙폭을 더 얕게 방어)")
        print("   ⚠️ 초과수익의 정체는 레버리지(베타)이지 종목선택 알파가 아니다.")
        print("      레짐 필터의 실제 기여는 '수익'이 아니라 'MDD 절단(리스크 관리)'으로 읽어야 한다.")
    else:
        print("⚠️ 레짐/벤치마크 결과가 모두 필요합니다(데이터 부족 또는 오류).")
    print("=" * 96)


if __name__ == "__main__":
    main()
