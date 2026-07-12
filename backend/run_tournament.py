import sys
import os

def bootstrap_venv():
    """공식 backend/venv 가상환경 파이썬으로 자가 프로세스 치환을 수행합니다."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if os.name == "nt":  # Windows
        venv_python = os.path.join(current_dir, "venv", "Scripts", "python.exe")
    else:  # macOS / Linux
        venv_python = os.path.join(current_dir, "venv", "bin", "python")
        
    if os.path.exists(venv_python) and os.path.abspath(sys.executable) != os.path.abspath(venv_python):
        try:
            os.execv(venv_python, [venv_python] + sys.argv)
        except Exception as e:
            print(f"[Launcher] 가상환경 치환 실패: {e}")

bootstrap_venv()

import asyncio
import pandas as pd
from datetime import datetime
import argparse
from concurrent.futures import ProcessPoolExecutor
from app.bot.backtest_engine import BacktestSimulator
from app.bot.backtest_metrics import assess_strategy_report
from app.translations.translator import Translator


# Force stdout to be utf-8 to avoid Windows CP949 encoding crash
import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 백테스트 후보의 단일 원장(SSOT)은 DB strategies 테이블(활성 전략)이다.
# 아래 튜플은 DB 조회가 불가능할 때만 쓰는 안전 폴백이다(직접 수정 지양).
_FALLBACK_STRATEGIES = (
    "antigravity_surge",
    "regime_sniper",
    "phoenix_bounce",
    "hurst_adaptive",
    "kalman_pairs",
    "chaikin_atr",
    "sentiment_fomo",
    "macro_momentum",
    "obi_ofa",
    "volatility_regime",
    "gex_pinning",
    "pca_knn",
    "sortino_momentum",
    "lava_volume",
    "td_sequential",
    "donchian_breakout",
    "opening_range_breakout",
)

# 백테스트 후보에서 제외할 비-전략 키.
# benchmark_qqq_hold는 QQQ 단순보유(=벤치마크 그 자체)라 후보에서 뺀다.
_NON_TRADEABLE_KEYS = frozenset({"benchmark_qqq_hold"})


def load_tournament_strategies():
    """토너먼트 후보 목록을 DB strategies 테이블(활성)에서 도출한다.

    - 벤치마크 헬퍼(benchmark_qqq_hold)는 제외한다.
    - DB 접근 실패/빈 테이블이면 _FALLBACK_STRATEGIES로 안전 폴백한다.
    메인 프로세스에서 1회만 호출한다(자식 프로세스는 키를 인자로 전달받음).
    """
    try:
        from app.core.database import SessionLocal
        from app.core.models import Strategy

        db = SessionLocal()
        try:
            rows = [
                row[0]
                for row in db.query(Strategy.strategy_type)
                .filter(Strategy.is_active == True)  # noqa: E712
                .all()
            ]
        finally:
            db.close()

        keys = tuple(sorted(k for k in rows if k and k not in _NON_TRADEABLE_KEYS))
        if keys:
            print(f" • 후보 소스: DB strategies 테이블 (활성 {len(keys)}종, 벤치마크 제외)")
            return keys
        print(" [⚠️] DB strategies 테이블이 비어 있어 폴백 목록을 사용합니다.")
    except Exception as e:
        print(f" [⚠️] DB 후보 로딩 실패({e}) → 폴백 목록({len(_FALLBACK_STRATEGIES)}종) 사용")
    return _FALLBACK_STRATEGIES


def run_single_strategy_sync(strategy_key, tickers, start_date, end_date, interval, cash, tickers_data, qqq_data):
    """
    멀티프로세싱 프로세스 내에서 개별 전략의 백테스트 연산을 독립 수행하는 동기식 탑 레벨 래퍼.
    지표 계산(prepare_data)을 서브프로세스 내부에서 각자 수행하여 IPC 피클링 오버헤드를 원천 차단합니다.
    """
    import asyncio
    sim = BacktestSimulator(
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        initial_cash=cash,
        strategy_type=strategy_key
    )
    # 원본 시세 데이터 주입
    sim.tickers_data = tickers_data
    sim.qqq_data = qqq_data
    
    # 서브프로세스 내에서 로컬로 지표 연산 및 타임라인 구축 실행
    asyncio.run(sim.prepare_data())
    
    try:
        report = sim.run()
        if "error" not in report:
            assessment = assess_strategy_report(strategy_key, report)
            name = Translator.translate_strategy(strategy_key, "ko")
            return {
                "key": strategy_key,
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
                "qqq_bench_return_rate": report.get("qqq_bench_return_rate", 0.0),
                **assessment,
            }
        else:
            return {"key": strategy_key, "error": report["error"]}
    except Exception as e:
        return {"key": strategy_key, "error": str(e)}

async def main():
    import json
    import os
    
    parser = argparse.ArgumentParser(description="StockAuto v2.0 대규모 다차원 토너먼트 배틀")
    parser.add_argument("--tickers_file", type=str, default="tickers.json", help="티커 JSON 파일 경로")
    parser.add_argument("--result_json", type=str, default="", help="우승 전략 결과를 저장할 JSON 파일 경로 (옵션)")
    parser.add_argument("--start", type=str, default="2026-01-01", help="시작 날짜 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2026-05-30", help="종료 날짜 (YYYY-MM-DD)")
    parser.add_argument("--interval", type=str, default="1h", help="데이터 타임프레임 인터벌 (1d, 1h, 15m, 5m)")
    parser.add_argument("--cash", type=float, default=10000.0, help="시작 예수금 (USD)")
    parser.add_argument("--download_only", action="store_true", help="시세 데이터 다운로드 및 캐시 적재만 수행하고 종료")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.tickers_file):
        raise FileNotFoundError(f"\n[❌ CRITICAL ERROR] Ticker file '{args.tickers_file}' is missing!")
        
    with open(args.tickers_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        tickers_list = [item["ticker"] for item in data]
        
    print("==========================================================================")
    print(" 🏆 StockAuto v2.0 역사적 전략 토너먼트 배틀 기동 (Parallel Mode)")
    print("==========================================================================")
    print(f" • 대상 종목군 : {args.tickers_file} ({len(tickers_list)}개 종목)")
    print(f" • 검증 기간   : {args.start} ~ {args.end}")
    print(f" • 타임프레임  : {args.interval}")
    print(f" • 시작 예수금 : ${args.cash:,.2f} USD")
    print("==========================================================================\n")
    
    Translator.load_cache()
    
    # 1단계: 시세 데이터 1회 통합 다운로드 (yfinance 병렬/벌크)
    print(" ⏳ [1단계/3] 대상 종목군 시세 및 QQQ 지수 데이터 사전 다운로드 중...")
    dummy_sim = BacktestSimulator(
        tickers=tickers_list,
        start_date=args.start,
        end_date=args.end,
        interval=args.interval,
        initial_cash=args.cash,
        strategy_type="strategy_a",
        download_only=True # 메인에서는 무조건 다운로드만 수행해 지표 연산 중복과 오버헤드를 방지
    )
    await dummy_sim.prepare_data()
    
    tickers_data = dummy_sim.tickers_data
    qqq_data = dummy_sim.qqq_data
    
    print(f"   ➔ 시세 데이터 수집 완료! (실제 수집 종목 수: {len(tickers_data)}개)")
    
    if args.download_only:
        print("   ➔ [--download_only] 옵션이 활성화되었습니다. 수집 및 Parquet 캐싱을 성공적으로 마치고 프로그램을 종료합니다.")
        # --result_json 이 주어지면 실제 로드된 유니버스(정제 목록)를 덤프한다.
        # 소비자(사전 정제 러너)가 이 목록으로 죽은 티커를 걸러낸다.
        if args.result_json:
            os.makedirs(os.path.dirname(args.result_json) if os.path.dirname(args.result_json) else ".", exist_ok=True)
            with open(args.result_json, "w", encoding="utf-8") as f:
                json.dump({"universe": sorted(tickers_data.keys())}, f, ensure_ascii=False, indent=2)
            print(f"   ➔ 로드된 유니버스 {len(tickers_data)}종을 {args.result_json} 에 저장했습니다.")
        return
        
    print(" ⏳ [2단계/3] 멀티프로세싱 CPU 병렬 백테스팅 가동 중...")
    
    results = []
    
    # CPU 논리 코어 개수에 맞춰 ProcessPoolExecutor 생성
    loop = asyncio.get_running_loop()
    tournament_strategies = load_tournament_strategies()
    print(f"   ➔ 이번 대항전 후보 전략 수: {len(tournament_strategies)}종")

    with ProcessPoolExecutor() as executor:
        tasks = []
        for key in tournament_strategies:
            # ProcessPoolExecutor의 동기 실행을 asyncio 비동기 세션으로 브릿징
            task = loop.run_in_executor(
                executor,
                run_single_strategy_sync,
                key,
                tickers_list,
                args.start,
                args.end,
                args.interval,
                args.cash,
                tickers_data,
                qqq_data
            )
            tasks.append(task)
            
        completed_runs = await asyncio.gather(*tasks)
        
        for r in completed_runs:
            if "error" not in r:
                results.append(r)
                print(
                    f"   ➔ [{r['name']}] 완료! 수익률: {r['total_return_rate']:+.2f}%"
                    f" | Sharpe: {r['sharpe_ratio']:.2f}"
                    f" | MDD: {r['mdd']:.2f}%"
                    f" | 선발점수: {r['selection_score']:.2f}"
                    f" | 등급: {r['confidence_grade']}"
                )
            else:
                print(f"   ❌ 전략 [{r['key']}] 연산 에러: {r['error']}")
                
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
    
    # QQQ 단순보유 벤치마크 수익률
    qqq_bench_rate = results[0]["qqq_bench_return_rate"] if results else 0.0
    print(f" 📊 QQQ 단순 보유 (B&H) 누적 수익률: {qqq_bench_rate:+.2f}%")
    print("-" * 115)
    
    print(f"{'순위':<2} | {'전략 명칭':<30} | {'점수':<6} | {'등급':<4} | {'수익률':<8} | {'Sharpe':<7} | {'MDD':<7} | {'QQQ대비 초과'} | {'선발'}")
    print("-" * 115)
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
        alpha_rate = r['total_return_rate'] - r['qqq_bench_return_rate']
        print(
            f"{rank:<2} | {display_name:<30} | {r['selection_score']:>5.2f}"
            f" | {r['confidence_grade']:^4} | {r['total_return_rate']:>+7.2f}%"
            f" | {r['sharpe_ratio']:>7.2f} | {r['mdd']:>6.2f}% | {alpha_rate:>+11.2f}% | {eligible}"
        )
    print("==========================================================================\n")
    
    # Generate Markdown Table for Docs
    markdown_table = f"### 📊 백테스트 대항전 성적표 (유니버스: {os.path.basename(args.tickers_file)} | {args.start} ~ {args.end})\n"
    markdown_table += f"**QQQ 단순보유(B&H) 수익률**: `{qqq_bench_rate:+.2f}%`\n\n"
    markdown_table += "| 순위 | 전략 명칭 | 선발 점수 | 신뢰등급 | 데이터 근거 | 누적 수익률 | Sharpe | MDD | QQQ 대비 초과 | 선발 여부 |\n"
    markdown_table += "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n"
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
        alpha_rate = r['total_return_rate'] - r['qqq_bench_return_rate']
        markdown_table += (
            f"| {rank} | {bold_prefix}{display_name}{bold_suffix}"
            f" | {r['selection_score']:.2f} | {r['confidence_grade']}"
            f" | {r['data_basis']} | {r['total_return_rate']:+.2f}%"
            f" | {r['sharpe_ratio']:.2f} | {r['mdd']:.2f}% | {alpha_rate:+.2f}% | {eligible} |\n"
        )
        
    print("📝 마크다운 성적표 코드:")
    print(markdown_table)
    
    # 우승 전략 결과를 JSON 파일로 저장 (run_all_tournaments.py 등 외부 소비자용)
    if args.result_json and results:
        winner = results[0]
        alpha_rate = winner['total_return_rate'] - winner['qqq_bench_return_rate']
        # 전체 리더보드(모든 전략의 알파)를 저장한다.
        # 점수 우승자만이 아니라 "알파 1위"를 셀별로 뽑기 위해 소비자가 사용한다.
        leaderboard = [
            {
                "key": r['key'],
                "name": r['name'],
                "total_return_rate": r['total_return_rate'],
                "qqq_bench_return_rate": r['qqq_bench_return_rate'],
                "alpha": r['total_return_rate'] - r['qqq_bench_return_rate'],
                "sharpe_ratio": r['sharpe_ratio'],
                "mdd": r['mdd'],
                "selection_score": r['selection_score'],
                "confidence_grade": r['confidence_grade'],
                "selection_eligible": r['selection_eligible'],
            }
            for r in results
        ]
        result_data = {
            "winner_key": winner['key'],
            "winner_name": winner['name'],
            "total_return_rate": winner['total_return_rate'],
            "qqq_bench_return_rate": winner['qqq_bench_return_rate'],
            "alpha": alpha_rate,
            "sharpe_ratio": winner['sharpe_ratio'],
            "mdd": winner['mdd'],
            "selection_score": winner['selection_score'],
            "confidence_grade": winner['confidence_grade'],
            "selection_eligible": winner['selection_eligible'],
            "leaderboard": leaderboard,
        }
        os.makedirs(os.path.dirname(args.result_json) if os.path.dirname(args.result_json) else ".", exist_ok=True)
        with open(args.result_json, "w", encoding="utf-8") as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 우승 전략 JSON 저장 완료: {args.result_json}")

if __name__ == "__main__":
    asyncio.run(main())
