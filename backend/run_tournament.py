import asyncio
import os
import pandas as pd
from datetime import datetime
from app.bot.backtest_engine import BacktestSimulator
from app.bot.backtest_metrics import assess_strategy_report
from app.translations.translator import Translator

# Force stdout to be utf-8 to avoid Windows CP949 encoding crash
import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

TOURNAMENT_STRATEGIES = (
    "strategy_a", "strategy_b", "strategy_c", "exploded_c", "senior_simple",
    "qullamaggie", "obv_only", "rsi_bb_only", "ema_only", "vwap_only",
    "orb_only", "rsi2_connors", "bb_squeeze", "regime_switching",
    "episodic_pivot", "vcp_breakout", "pairs_trading", "weekend_trend",
    "darvas_box", "zscore_reversion", "heikin_ashi", "ichimoku_kumo",
    "parabolic_sar", "supertrend", "hma_swing", "coppock_curve", "elder_ray",
    "woodies_cci", "pivot_point", "fisher_transform", "keltner_reversion",
    "larry_williams", "volume_filtered_cross", "pdufa_calendar",
    "insider_buying", "short_squeeze", "dark_pool", "gamma_flip", "max_pain",
    "wyckoff_spring", "morning_gap_fade", "social_buzz", "cross_asset",
    "order_flow", "volume_profile", "turn_of_month", "supernova",
    "panic_dip_buy", "first_red", "pump_run_pull", "pre_gapper", "float_rot",
    "sympathy", "warrant_arb", "earn_drift", "offering_reb", "parabolic_blow",
    "double_bot", "overnight_gap", "death_rebound", "relative_str",
    "bollinger_tr", "macd_diverg", "stoch_extreme", "keltner_tr", "triple_ema",
    "range_contra", "vol_spike_brk", "pivot_rebound", "vix_hedging",
    "premarket_breakout", "trend_stabilization",
)


async def main():
    import json
    tickers_file = "tickers.json"
    if not os.path.exists(tickers_file):
        raise FileNotFoundError(f"\n[❌ CRITICAL ERROR] Ticker configuration file '{tickers_file}' is missing!\n"
                                f"Please ensure '{tickers_file}' is present in the backend/ directory before running.")
    with open(tickers_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        tickers_list = [item["ticker"] for item in data]
    start_date = "2026-01-01"
    end_date = "2026-05-30"
    interval = "1h"
    cash = 10000.0

    print("==========================================================================")
    print(" 🏆 StockAuto v2.0 역사적 전략 토너먼트 배틀 기동 (Tournament Mode)")
    print("==========================================================================")
    print(f" • 대상 종목군 : {', '.join(tickers_list)}")
    print(f" • 검증 기간   : {start_date} ~ {end_date}")
    print(f" • 타임프레임  : {interval}")
    print(f" • 시작 예수금 : ${cash:,.2f} USD")
    print("==========================================================================\n")

    Translator.load_cache()
    results = []

    for key in TOURNAMENT_STRATEGIES:
        name = Translator.translate_strategy(key, "ko")
        print(f" ⏳ [{name}] 데이터 준비 및 시뮬레이션 계산 중...")
        sim = BacktestSimulator(
            tickers=tickers_list,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            initial_cash=cash,
            strategy_type=key
        )
        
        try:
            await sim.prepare_data()
            report = sim.run()
            
            if "error" not in report:
                assessment = assess_strategy_report(key, report)
                results.append({
                    "key": key,
                    "name": name,
                    "final_value": report["final_value"],
                    "total_pnl": report["total_pnl"],
                    "total_return_rate": report["total_return_rate"],
                    "mdd": report["mdd"],
                    "total_trades": report["total_trades"],
                    "win_rate": report["win_rate"],
                    "profit_factor": report["profit_factor"],
                    "sharpe_ratio": report["sharpe_ratio"],
                    "sortino_ratio": report["sortino_ratio"],
                    "calmar_ratio": report["calmar_ratio"],
                    **assessment,
                })
                print(
                    f"   ➔ 완료! 수익률: {report['total_return_rate']:+.2f}%"
                    f" | Sharpe: {report['sharpe_ratio']:.2f}"
                    f" | MDD: {report['mdd']:.2f}%"
                    f" | 선발점수: {assessment['selection_score']:.2f}"
                    f" | 등급: {assessment['confidence_grade']}"
                )
            else:
                print(f"   ❌ 에러: {report['error']}")
        except Exception as e:
            print(f"   ❌ 오류 발생: {e}")

    results.sort(
        key=lambda result: (
            result["selection_eligible"],
            result["selection_score"],
        ),
        reverse=True,
    )

    print("\n==========================================================================")
    print(" 🏆 StockAuto 전략 대항전 최종 순위표 (Leaderboard)")
    print("==========================================================================")
    
    # Print formatted console table
    print(f"{'순위':<2} | {'전략 명칭':<30} | {'점수':<6} | {'등급':<4} | {'수익률':<8} | {'Sharpe':<7} | {'MDD':<7} | {'선발'}")
    print("-" * 105)
    for rank, r in enumerate(results, 1):
        if rank == 1:
            rank_emoji = "🥇 "
        elif rank == 2:
            rank_emoji = "🥈 "
        elif rank == 3:
            rank_emoji = "🥉 "
        elif r['key'] == "strategy_a":
            rank_emoji = "🅅1 "
        elif r['key'] in ["regime_switching", "senior_simple"]:
            rank_emoji = "🅅2 "
        elif r['key'] == "strategy_b":
            rank_emoji = "🅱 "
        elif r['key'] in ["strategy_c", "exploded_c"]:
            rank_emoji = "🅲 "
        else:
            rank_emoji = "⚙️ "
        display_name = rank_emoji + r['name']
        eligible = "가능" if r["selection_eligible"] else "제외"
        print(
            f"{rank:<2} | {display_name:<30} | {r['selection_score']:>5.2f}"
            f" | {r['confidence_grade']:^4} | {r['total_return_rate']:>+7.2f}%"
            f" | {r['sharpe_ratio']:>7.2f} | {r['mdd']:>6.2f}% | {eligible}"
        )
    print("==========================================================================\n")

    # Generate Markdown Table for Docs
    markdown_table = "| 순위 | 전략 명칭 | 선발 점수 | 신뢰등급 | 데이터 근거 | 누적 수익률 | Sharpe | MDD | 선발 여부 |\n"
    markdown_table += "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n"
    for rank, r in enumerate(results, 1):
        if rank == 1:
            rank_emoji = "🥇 "
        elif rank == 2:
            rank_emoji = "🥈 "
        elif rank == 3:
            rank_emoji = "🥉 "
        elif r['key'] == "strategy_a":
            rank_emoji = "🅅1 "
        elif r['key'] in ["regime_switching", "senior_simple"]:
            rank_emoji = "🅅2 "
        elif r['key'] == "strategy_b":
            rank_emoji = "🅱 "
        elif r['key'] in ["strategy_c", "exploded_c"]:
            rank_emoji = "🅲 "
        else:
            rank_emoji = "⚙️ "
        display_name = rank_emoji + r['name']
        bold_prefix = "**" if rank == 1 else ""
        bold_suffix = "**" if rank == 1 else ""
        eligible = "가능" if r["selection_eligible"] else "제외"
        markdown_table += (
            f"| {rank} | {bold_prefix}{display_name}{bold_suffix}"
            f" | {r['selection_score']:.2f} | {r['confidence_grade']}"
            f" | {r['data_basis']} | {r['total_return_rate']:+.2f}%"
            f" | {r['sharpe_ratio']:.2f} | {r['mdd']:.2f}% | {eligible} |\n"
        )

    print("📝 마크다운 성적표 코드:")
    print(markdown_table)

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
