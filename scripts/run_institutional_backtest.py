import os
import sys
import numpy as np
import pandas as pd
import yfinance as yf

# 루트 경로 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.strategies.institutional_follow import InstitutionalFollow


def compute_atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high = df['High']
    low = df['Low']
    close_prev = df['Close'].shift(1)
    
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window).mean()


def fetch_qqq_benchmark(period: str = "3y") -> float:
    """QQQ 단순보유(buy-and-hold) 총수익률(%)을 공통 벤치마크로 산출.

    종목별 bh_return과 동일한 관례(워밍업 이후 iloc[50] 시가 진입 → 마지막 종가)로
    계산해 alpha_vs_qqq 비교가 사과-대-사과가 되도록 한다.
    """
    df = yf.Ticker("QQQ").history(period=period, interval="1d")
    if df.empty or len(df) < 60:
        raise RuntimeError("QQQ 벤치마크 데이터를 가져오지 못했습니다.")
    return ((df.iloc[-1]['Close'] - df.iloc[50]['Open']) / df.iloc[50]['Open']) * 100.0


def run_backtest_for_symbol(symbol: str, strategy: InstitutionalFollow, period: str = "3y",
                            qqq_benchmark: float = 0.0) -> dict:
    df = yf.Ticker(symbol).history(period=period, interval="1d")
    if df.empty or len(df) < 60:
        return None

    df['sma20'] = df['Close'].rolling(20).mean()
    df['sma50'] = df['Close'].rolling(50).mean()
    df['vol_sma20'] = df['Volume'].rolling(20).mean()
    df['atr'] = compute_atr(df, 14)

    cash = 10000.0
    position_qty = 0.0
    entry_price = 0.0
    highest_price_since_entry = 0.0
    trades = []
    daily_equity = []
    
    fee_rate = 0.0010  # 0.10% 수수료 + 슬리피지

    # 지표 워밍업 이후부터 백테스트
    for i in range(50, len(df)):
        row = df.iloc[i]
        date = df.index[i]
        close = row['Close']
        open_next = df.iloc[i + 1]['Open'] if (i + 1 < len(df)) else close
        
        current_equity = cash + (position_qty * close)
        daily_equity.append(current_equity)

        if position_qty == 0.0:
            # 진입 신호 판정
            score = strategy.calculate_score(row, regime="BULLISH", is_entry=True)
            if score >= 85.0 and (i + 1 < len(df)):
                # 익일 시가 진입 (Lookahead 차단)
                buy_price = open_next * (1.0 + fee_rate)
                invest_amount = cash * strategy.base_allocation_pct
                position_qty = invest_amount / buy_price
                cash -= invest_amount
                entry_price = buy_price
                highest_price_since_entry = buy_price
        else:
            highest_price_since_entry = max(highest_price_since_entry, close)
            atr = row['atr']
            sl_pct = strategy.get_stop_loss_pct(atr, close)
            stop_price = entry_price * (1.0 - sl_pct / 100.0)

            # 청산 신호 판정
            score = strategy.calculate_score(row, regime="BULLISH", is_entry=False)
            exit_triggered = False
            exit_reason = ""

            if close <= stop_price:
                exit_triggered = True
                exit_reason = f"손절(-{sl_pct:.1f}%)"
            elif score < 40.0:
                exit_triggered = True
                exit_reason = "수급/추세 붕괴"
            elif close >= entry_price * (1.0 + strategy.min_smart_exit_profit / 100.0) and close < highest_price_since_entry * 0.965:
                exit_triggered = True
                exit_reason = "트레일링 익절"

            if exit_triggered and (i + 1 < len(df)):
                sell_price = open_next * (1.0 - fee_rate)
                revenue = position_qty * sell_price
                cash += revenue
                pnl_pct = ((sell_price - entry_price) / entry_price) * 100.0
                trades.append({
                    'entry_date': date,
                    'symbol': symbol,
                    'entry_price': entry_price,
                    'exit_price': sell_price,
                    'pnl_pct': pnl_pct,
                    'reason': exit_reason
                })
                position_qty = 0.0
                entry_price = 0.0

    final_equity = cash + (position_qty * df.iloc[-1]['Close'])
    total_return = ((final_equity - 10000.0) / 10000.0) * 100.0
    
    # MDD 계산
    eq_series = pd.Series(daily_equity)
    cummax = eq_series.cummax()
    drawdown = (eq_series - cummax) / cummax
    mdd = abs(drawdown.min()) * 100.0 if not drawdown.empty else 0.0

    # 승률 계산
    win_trades = [t for t in trades if t['pnl_pct'] > 0]
    win_rate = (len(win_trades) / len(trades) * 100.0) if trades else 0.0

    # Benchmark 단순 보유 수익률
    bh_return = ((df.iloc[-1]['Close'] - df.iloc[50]['Open']) / df.iloc[50]['Open']) * 100.0

    # QQQ 총수익 벤치마크 대비 알파 (전략 raw수익 - QQQ 단순보유수익)
    # 양수여야 비로소 "QQQ를 이겼다"고 말할 수 있다. bh_return(자기 단순보유)과 혼동 금지.
    alpha_vs_qqq = total_return - qqq_benchmark

    return {
        'symbol': symbol,
        'final_equity': final_equity,
        'total_return': total_return,
        'bh_return': bh_return,
        'qqq_benchmark': qqq_benchmark,
        'alpha_vs_qqq': alpha_vs_qqq,
        'mdd': mdd,
        'trade_count': len(trades),
        'win_rate': win_rate,
        'trades': trades
    }


def main():
    print("=" * 70)
    print("🚀 [StockAuto] 기관/외국인 스마트머니 수급 추종 (InstitutionalFollow) 3년 백테스트")
    print("=" * 70)

    strategy = InstitutionalFollow()
    symbols = ["NVDA", "AAPL", "MSFT", "TSLA", "AMD", "QQQ", "SPY"]

    # 공통 벤치마크: QQQ 총수익. 전략이 이걸 넘어야만 "QQQ를 이겼다".
    qqq_benchmark = fetch_qqq_benchmark(period="3y")
    print(f"📈 QQQ 총수익 벤치마크 (3년 단순보유): {qqq_benchmark:+6.2f}%")
    print("-" * 70)

    results = []
    all_trades = []

    for sym in symbols:
        res = run_backtest_for_symbol(sym, strategy, period="3y", qqq_benchmark=qqq_benchmark)
        if res:
            results.append(res)
            all_trades.extend(res['trades'])
            print(f"[{sym:5s}] 전략: {res['total_return']:+7.2f}% | 자기단순보유: {res['bh_return']:+7.2f}% | QQQ대비 알파: {res['alpha_vs_qqq']:+7.2f}%p | MDD: {res['mdd']:5.2f}% | 승률: {res['win_rate']:5.1f}% ({res['trade_count']}회)")

    print("-" * 70)
    avg_return = np.mean([r['total_return'] for r in results])
    avg_bh = np.mean([r['bh_return'] for r in results])
    avg_alpha = np.mean([r['alpha_vs_qqq'] for r in results])
    avg_mdd = np.mean([r['mdd'] for r in results])
    total_trades = len(all_trades)
    overall_win_rate = (len([t for t in all_trades if t['pnl_pct'] > 0]) / total_trades * 100.0) if total_trades > 0 else 0.0
    beat_qqq_count = len([r for r in results if r['alpha_vs_qqq'] > 0])

    print(f"📊 [유니버스 평균 성과] (거래비용 0.10% 반영 / Lookahead 차단)")
    print(f" - 평균 전략 수익률   : {avg_return:+7.2f}%")
    print(f" - 평균 자기단순보유   : {avg_bh:+7.2f}%")
    print(f" - QQQ 총수익 벤치마크 : {qqq_benchmark:+7.2f}%")
    print(f" - 평균 QQQ대비 알파   : {avg_alpha:+7.2f}%p   ({beat_qqq_count}/{len(results)}종목이 QQQ 초과)")
    print(f" - 평균 최대낙폭(MDD)  : {avg_mdd:5.2f}%")
    print(f" - 전체 거래 승률      : {overall_win_rate:5.1f}% (총 {total_trades}회 거래)")
    print("=" * 70)

    # 정직한 판정: 평균 알파가 양수여야 비로소 QQQ를 이긴 것.
    if avg_alpha > 0:
        print(f"✅ 판정: 전략이 QQQ 총수익을 평균 {avg_alpha:+.2f}%p 초과함.")
    else:
        print(f"❌ 판정: 전략은 QQQ 총수익을 이기지 못함 (평균 알파 {avg_alpha:+.2f}%p).")
        print("   → 낮은 MDD는 실력이 아니라 base_allocation_pct 저노출 + 잦은 현금대기 효과.")
        print("   → QQQ 총수익 초과가 목표라면 능동 타이밍이 아닌 leveraged_regime(레버리지=베타) 경로를 참조.")

    # Assert check for basic sanity
    assert len(results) > 0, "Backtest must produce results for active symbols."
    print("✅ 백테스트 검증 완료: 정상 수행 되었습니다.")


if __name__ == "__main__":
    main()
