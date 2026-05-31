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

    strategies = {
        "strategy_a": "전략 A (태초 v1.0)",
        "strategy_b": "전략 B (실험용) 🧪",
        "strategy_c": "전략 C (11대 복합)",
        "exploded_c": "전략 C-폭발형 (즉시 풀비중) 🔥",
        "senior_simple": "시니어 단순화 (Strategy S)",
        "qullamaggie": "쿨라매기 돌파 (Qullamaggie)",
        "obv_only": "차트픽 OBV 매집 (OBV Only)",
        "rsi_bb_only": "RSI 볼린저밴드 (RSI BB Only)",
        "ema_only": "EMA 이평정배열 (EMA Only)",
        "vwap_only": "VWAP 세력지지선 (VWAP Only)",
        "orb_only": "토비크라벨 ORB (ORB Only)",
        "rsi2_connors": "래리코너스 RSI 2 (RSI 2 Only)",
        "bb_squeeze": "존카터 BB스퀴즈 (TTM Squeeze)",
        "regime_switching": "마스터 레짐스위칭 (Regime Switching)",
        "episodic_pivot": "에피소딕 피벗 (Episodic Pivot)",
        "vcp_breakout": "변동성 축소 패턴 (VCP)",
        "pairs_trading": "롱-숏 통계적 차익거래 (Pairs Trading)",
        "weekend_trend": "주말 추세 매매 (Weekend Trend)",
        "darvas_box": "다바스 박스 매매 (Darvas Box)",
        "zscore_reversion": "Z-스코어 평균회귀 (Z-Score Reversion)",
        "heikin_ashi": "하이킨아시 추세추종 (Heikin-Ashi)",
        "ichimoku_kumo": "일목균형표 구름대돌파 (Ichimoku)",
        "parabolic_sar": "파라볼릭 SAR 반전 (Parabolic SAR)",
        "supertrend": "슈퍼트렌드 모멘텀 (SuperTrend)",
        "hma_swing": "HMA 지연최소화 스윙 (HMA Swing)",
        "coppock_curve": "코폭커브 장기바닥 (Coppock Curve)",
        "elder_ray": "엘더레이 힘의균형 (Elder Ray)",
        "woodies_cci": "우디 CCI 고스트 (Woodies CCI)",
        "pivot_point": "피봇포인트 반전 (Pivot Point)",
        "fisher_transform": "피셔트랜스폼 정점반전 (Fisher)",
        "keltner_reversion": "켈트너채널 반전 (Keltner Reversion)",
        "larry_williams": "윌리엄스 %R 단기반전 (Williams %R)",
        "volume_filtered_cross": "거래량 필터 이평교차 (Volume Golden Cross)",
        "pdufa_calendar": "PDUFA 임상스윙 (PDUFA Run)",
        "insider_buying": "내부자 지분매수 (Insider Scan)",
        "short_squeeze": "숏스퀴즈 가속 (Short Squeeze)",
        "dark_pool": "다크풀 블록딜 (Dark Pool Scan)",
        "gamma_flip": "감마플립 셋업 (Gamma Flip)",
        "max_pain": "맥스페인 반전 (Max Pain)",
        "wyckoff_spring": "와이코프 스프링 (Wyckoff Spring)",
        "morning_gap_fade": "시초가 갭페이드 (Morning Fade)",
        "social_buzz": "소셜버즈 모멘텀 (Social Buzz)",
        "cross_asset": "자산간 금리필터 (Cross Asset)",
        "order_flow": "볼륨델타 오더플로 (Order Flow)",
        "volume_profile": "매물대 프로파일 (Volume POC)",
        "turn_of_month": "월말효과 계절성 (Turn of Month)",
        "supernova": "티모시 사이크스 슈퍼노바 (Supernova)",
        "panic_dip_buy": "모닝 패닉 딥 바잉 (Panic Dip)",
        "first_red": "퍼스트 레드 데이 숏 (First Red)",
        "pump_run_pull": "펌프 앤 런 눌림목 (Pump Pullback)",
        "pre_gapper": "프리마켓 갭 돌파 (Pre Gapper)",
        "float_rot": "유통주 회전율 돌파 (Float Rotation)",
        "sympathy": "테마 2등주 짝짓기 (Sympathy Play)",
        "warrant_arb": "워런트 괴리 매수 (Warrant Arb)",
        "earn_drift": "깜짝실적 갭앤드리프트 (EGAD)",
        "offering_reb": "유증 악재 소멸 반등 (Offering Reb)",
        "parabolic_blow": "파라볼릭 폭발 청산 (Parabolic Blow)",
        "double_bot": "이중바닥 W 돌파 (Double Bottom)",
        "overnight_gap": "오버나이트 갭 사냥 (Overnight Gap)",
        "death_rebound": "역배열 극점 평균회귀 (Death Rebound)",
        "relative_str": "지수 대비 강세 주도주 (Relative Strength)",
        "bollinger_tr": "볼밴 상단 돌파 추세 (Bollinger Trend)",
        "macd_diverg": "MACD 다이버전스 (MACD Divergence)",
        "stoch_extreme": "스토캐스틱 극점 반전 (Stoch Extreme)",
        "keltner_tr": "켈트너 채널 추세추종 (Keltner Trend)",
        "triple_ema": "삼중 EMA 정배열 교차 (Triple EMA)",
        "range_contra": "변동성 캔들 수축 돌파 (Range Contraction)",
        "vol_spike_brk": "10배 거래량 장대양봉 (Vol Spike)",
        "pivot_rebound": "피봇 저항돌파/지지반등 (Pivot Rebound)",
        "vix_hedging": "VIX 변동성 연계 헷지 (VIX Hedging)"
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
    print(f"{'순위':<2} | {'전략 명칭':<30} | {'최종자산':<11} | {'누적수익률':<7} | {'PF':<5} | {'MDD':<6} | {'거래수'}")
    print("-" * 80)
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
        print(f"{rank:<2} | {display_name:<30} | ${r['final_value']:<10,.2f} | {r['total_return_rate']:>+6.2f}% | {r['profit_factor']:<5.2f} | {r['mdd']:>5.2f}% | {r['total_trades']:<5}회")
    print("==========================================================================\n")

    # Generate Markdown Table for Docs
    markdown_table = "| 순위 | 전략 명칭 | 최종 자산 | 누적 수익률 | 프로핏 팩터 (PF) | 최대 낙폭 (MDD) | 거래 횟수 |\n"
    markdown_table += "| :---: | :--- | :--- | :---: | :---: | :---: | :---: |\n"
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
        markdown_table += f"| {rank} | {bold_prefix}{display_name}{bold_suffix} | ${r['final_value']:,.2f} | {bold_prefix}{r['total_return_rate']:+.2f}%{bold_suffix} | {r['profit_factor']:.2f} | {r['mdd']:.2f}% | {r['total_trades']}회 |\n"

    print("📝 마크다운 성적표 코드:")
    print(markdown_table)

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
