import asyncio
import os
import pandas as pd
from datetime import datetime
from app.bot.backtest_engine import BacktestSimulator

# Force stdout to be utf-8 to avoid Windows CP949 encoding crash
import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def main():
    tickers_list = ["PLTR", "SMCI", "AMZN", "MSFT"]
    start_date = "2026-04-01"
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

    strategies = {
        "strategy_a": "🔴 전략 A (태초 10% 비중 + 하드 컷)",
        "strategy_b": "🟠 전략 B (채점 분리 + 40% 비중 + 1% 익절)",
        "strategy_c": "🏆 전략 C (익절 2.5% + 불타기 완화)",
        "exploded_c": "🔥 전략 C-폭발형 (즉시 풀비중 + 넓은 손절선)",
        "senior_simple": "시니어 단순화 (Strategy S)",
        "qullamaggie": "쿨라매기 돌파 (Qullamaggie)",
        "obv_only": "차트픽 OBV 매집 (OBV Only)",
        "rsi_bb_only": "RSI 볼린저밴드 (RSI BB Only)",
        "ema_only": "EMA 이평정배열 (EMA Only)",
        "vwap_only": "VWAP 세력지지선 (VWAP Only)",
        "orb_only": "토비크라벨 ORB (ORB Only)",
        "rsi2_connors": "래리코너스 RSI 2 (RSI 2 Only)",
        "bb_squeeze": "존카터 BB스퀴즈 (TTM Squeeze)",
        "regime_switching": "마스터 레짐스위칭 (Regime Switching)"
    }

    results = []

    for key, name in strategies.items():
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
                results.append({
                    "key": key,
                    "name": name,
                    "final_value": report["final_value"],
                    "total_pnl": report["total_pnl"],
                    "total_return_rate": report["total_return_rate"],
                    "mdd": report["mdd"],
                    "total_trades": report["total_trades"],
                    "win_rate": report["win_rate"],
                    "profit_factor": report["profit_factor"]
                })
                print(f"   ➔ 완료! 자산: ${report['final_value']:,.2f} | PnL: ${report['total_pnl']:+,.2f} ({report['total_return_rate']:+.2f}%) | PF: {report['profit_factor']:.2f} | MDD: {report['mdd']:.2f}%")
            else:
                print(f"   ❌ 에러: {report['error']}")
        except Exception as e:
            print(f"   ❌ 오류 발생: {e}")

    # Sort results by return rate descending
    results.sort(key=lambda x: x["total_return_rate"], reverse=True)

    print("\n==========================================================================")
    print(" 🏆 StockAuto 전략 대항전 최종 순위표 (Leaderboard)")
    print("==========================================================================")
    
    # Print formatted console table
    print(f"{'순위':<2} | {'전략 명칭':<25} | {'최종자산':<11} | {'누적수익률':<7} | {'PF':<5} | {'MDD':<6} | {'거래수'}")
    print("-" * 75)
    for rank, r in enumerate(results, 1):
        print(f"{rank:<2} | {r['name']:<25} | ${r['final_value']:<10,.2f} | {r['total_return_rate']:>+6.2f}% | {r['profit_factor']:<5.2f} | {r['mdd']:>5.2f}% | {r['total_trades']:<5}회")
    print("==========================================================================\n")

    # Generate Markdown Table for Docs
    markdown_table = "| 순위 | 전략 명칭 | 최종 자산 | 누적 수익률 | 프로핏 팩터 (PF) | 최대 낙폭 (MDD) | 거래 횟수 |\n"
    markdown_table += "| :---: | :--- | :--- | :---: | :---: | :---: | :---: |\n"
    for rank, r in enumerate(results, 1):
        bold_prefix = "**" if rank == 1 else ""
        bold_suffix = "**" if rank == 1 else ""
        markdown_table += f"| {rank} | {bold_prefix}{r['name']}{bold_suffix} | ${r['final_value']:,.2f} | {bold_prefix}{r['total_return_rate']:+.2f}%{bold_suffix} | {r['profit_factor']:.2f} | {r['mdd']:.2f}% | {r['total_trades']}회 |\n"

    print("📝 마크다운 성적표 코드:")
    print(markdown_table)

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
