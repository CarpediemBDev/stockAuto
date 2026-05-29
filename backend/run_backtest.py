import argparse
import asyncio
import os
import pandas as pd
from datetime import datetime
from app.bot.backtest_engine import BacktestSimulator

# UTF-8 출력 보장 (한글 깨짐 방지)
import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def main():
    parser = argparse.ArgumentParser(description="StockAuto v2.0 역사적 백테스팅 CLI 실행기")
    parser.add_argument("--tickers", type=str, default="TSLA,NVDA,MSFT,AAPL", help="백테스트 대상 주식 티커들 (쉼표로 구분)")
    parser.add_argument("--start", type=str, default="2026-04-01", help="시작 날짜 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2026-05-30", help="종료 날짜 (YYYY-MM-DD)")
    parser.add_argument("--interval", type=str, default="1h", choices=["1m", "5m", "15m", "1h", "1d"], help="데이터 타임프레임 인터벌")
    parser.add_argument("--cash", type=float, default=10000.0, help="가상 시작 예수금 (USD)")
    
    args = parser.parse_args()
    
    tickers_list = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers_list:
        print("❌ 에러: 유효한 티커를 입력해주세요.")
        return

    print("==========================================================================")
    print(" 🚀 StockAuto v2.0 역사적 백테스팅 시스템 시뮬레이션 기동")
    print("==========================================================================")
    print(f" • 대상 종목군 : {', '.join(tickers_list)}")
    print(f" • 검증 기간   : {args.start} ~ {args.end}")
    print(f" • 타임프레임  : {args.interval}")
    print(f" • 시작 예수금 : ${args.cash:,.2f} USD")
    print("--------------------------------------------------------------------------")
    print(" ⏳ 1단계: 역사적 OHLCV 시세 및 QQQ 지수 데이터 병렬 다운로드 중...")
    
    # 시뮬레이터 인스턴스 생성
    sim = BacktestSimulator(
        tickers=tickers_list, 
        start_date=args.start, 
        end_date=args.end, 
        interval=args.interval, 
        initial_cash=args.cash
    )
    
    try:
        await sim.prepare_data()
    except Exception as e:
        print(f"❌ 데이터 수집 및 연산 실패: {e}")
        return
        
    if not sim.tickers_data:
        print("❌ 에러: 데이터가 유효한 종목이 단 하나도 없습니다. 티커명이나 범위를 확인하세요.")
        return
        
    print(f" • 시세 데이터 적재 성공! 실제 검증 종목: {list(sim.tickers_data.keys())}")
    print(" ⏳ 2단계: 크로노스 시간축 순차 시뮬레이션 루프 구동 중...")
    
    # 백테스트 시뮬레이션 가동
    report = sim.run()
    
    if "error" in report:
        print(f"❌ 시뮬레이션 실패: {report['error']}")
        return

    print("==========================================================================")
    print(" 🏆 백테스팅 최종 성적 보고서 (Backtest Performance Report)")
    print("==========================================================================")
    print(f" 💵 초기 자산   : ${report['initial_cash']:,.2f}")
    print(f" 💵 최종 자산   : ${report['final_value']:,.2f}")
    print(f" 📈 누적 실수익 : ${report['total_pnl']:+,.2f} ({report['total_return_rate']:+.2f}% 실수익률)")
    print(f" 📊 QQQ 지수 대비 초과실수익률: {report['total_return_rate'] - report['qqq_bench_return_rate']:+.2f}% (QQQ 단순보유: {report['qqq_bench_return_rate']:+.2f}%)")
    print(f" 📉 최대 낙폭 (MDD): {report['mdd']:.2f}%")
    print("--------------------------------------------------------------------------")
    print(f" 🔄 총 매매 횟수: {report['total_trades']} 회")
    print(f" 🎯 승률 (Win Rate)  : {report['win_rate']:.2f}%")
    print(f" ⚖️ 프로핏 팩터      : {report['profit_factor']:.2f}")
    print("==========================================================================")

    # 3. 거래 로그 상세 출력 (최근 15개 거래)
    trade_logs = report["trade_logs"]
    if trade_logs:
        print("\n 📝 최근 체결 거래 내역 (최근 15건 요약):")
        print("----------------------------------------------------------------------------------------------------")
        print(f"{'시간':<17} | {'종목':<5} | {'유형':<4} | {'수량':<4} | {'체결단가':<8} | {'실수익금':<10} | {'실수익률':<7} | {'체결사유'}")
        print("----------------------------------------------------------------------------------------------------")
        for log in trade_logs[-15:]:
            ts_str = log['timestamp'].strftime('%y-%m-%d %H:%M') if isinstance(log['timestamp'], datetime) else str(log['timestamp'])[:16]
            pnl_str = f"${log['realized_pnl']:+,.2f}" if log['trade_type'] == "SELL" else "-"
            ret_str = f"{log['return_rate']:+.2f}%" if log['trade_type'] == "SELL" else "-"
            print(f"{ts_str:<17} | {log['ticker']:<5} | {log['trade_type']:<4} | {log['quantity']:<4} | ${log['price']:<7.2f} | {pnl_str:<10} | {ret_str:<7} | {log['reason']}")
        print("----------------------------------------------------------------------------------------------------")

    print("==========================================================================")

if __name__ == "__main__":
    # Windows 비동기 정책 설정
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
