import asyncio
import hashlib
import json
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any
from app.bot.backtest_engine import BacktestSimulator
from app.bot.backtest_metrics import (
    assess_strategy_report,
    calculate_performance_metrics,
)
from app.strategies.strategy_factory import get_strategy
from app.core.logging import logger
from app.translations.translator import Translator


def _apply_strategy_display_names(results: list[dict]) -> list[dict]:
    for result in results:
        strategy_type = result.get("strategy_type")
        if strategy_type:
            result["name"] = Translator.translate_strategy(strategy_type, "ko")
    return results


def _build_tournament_cache_path(
    start_date: str,
    end_date: str,
    tickers_list: List[str] | None,
) -> Path:
    normalized_tickers = sorted({ticker.strip().upper() for ticker in tickers_list or [] if ticker.strip()})
    ticker_payload = ",".join(normalized_tickers) if normalized_tickers else "default"
    ticker_digest = hashlib.sha256(ticker_payload.encode("utf-8")).hexdigest()[:16]
    cache_dir = Path(__file__).resolve().parents[2] / "data" / "backtest_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / (
        f"tournament_v3_{start_date}_{end_date}_{len(normalized_tickers)}_{ticker_digest}.json"
    )

# 가상 DB 보유 레코드 모사 클래스
class MockHolding:
    def __init__(self, ticker, ticker_name, avg_price, quantity, highest_price, regime_mode, buy_stage, strategy_type):
        self.ticker = ticker
        self.ticker_name = ticker_name
        self.avg_price = avg_price
        self.quantity = quantity
        self.highest_price = highest_price
        self.regime_mode = regime_mode
        self.buy_stage = buy_stage
        self.strategy_type = strategy_type
        self.current_price = avg_price

def run_multi_strategy_sim(base_sim, slots_cfg, initial_cash, tickers_list):
    """격리형 멀티 전략 슬롯 매니저의 백테스트를 100% 동일한 데이터 축 위에서 시뮬레이션합니다."""
    # 전략 인스턴스 지연 생성
    strategies = {
        slot_key: get_strategy(cfg["strategy_key"])
        for slot_key, cfg in slots_cfg.items()
    }
    
    # 단일 계좌 가상 원장
    cash_balance = initial_cash
    holdings = []      # List of MockHolding
    trade_logs = []    # List of dict
    equity_curve = []  # List of dict
    
    # Whipsaw 노이즈 버퍼 연속 2회 가드 캐시
    breach_counts = {}
    
    # 재진입 방지 쿨다운 시간 기록 캐시
    sell_cooldowns = {}

    for step, t in enumerate(base_sim.timeline):
        qqq_row = base_sim.qqq_metrics.loc[t]
        sentiment = qqq_row['regime'] # BULLISH, BEARISH, NEUTRAL
        
        # 1. 시점 t 기준 유효한 종목 실시간 종가 파악
        current_prices = {}
        for ticker in base_sim.tickers_data:
            metrics = base_sim.processed_metrics[ticker]
            if t in metrics.index:
                current_prices[ticker] = float(metrics.loc[t, 'Close'])

        # 2. 실시간 평가자산 산출
        stock_value = 0.0
        for h in holdings:
            clean_ticker = h.ticker
            if clean_ticker in current_prices:
                h.current_price = current_prices[clean_ticker]
            stock_value += h.quantity * h.current_price
            
        total_asset = cash_balance + stock_value
        equity_curve.append({
            "timestamp": t.strftime('%Y-%m-%d %H:%M:%S') if hasattr(t, 'strftime') else str(t),
            "cash": cash_balance,
            "stock_value": stock_value,
            "total": total_asset
        })

        # 3. 실시간 격리 지갑 자산 분배
        slot_stock_values = {slot_key: 0.0 for slot_key in slots_cfg}
        for h in holdings:
            qty = h.quantity
            price = h.current_price
            
            slot_key = h.strategy_type
            if slot_key in slot_stock_values:
                slot_stock_values[slot_key] += qty * price
            else:
                if "regime_switching" in slot_stock_values:
                    slot_stock_values["regime_switching"] += qty * price

        slot_allocations = {}
        for slot_key, cfg in slots_cfg.items():
            if sentiment == "BULLISH":
                weight = cfg["weight_bullish"]
            else:
                weight = cfg["weight_bearish"]
                
            slot_total_asset = total_asset * weight
            slot_stock_val = slot_stock_values[slot_key]
            slot_cash = max(0.0, slot_total_asset - slot_stock_val)
            slot_cash = min(cash_balance, slot_cash)
            
            slot_allocations[slot_key] = {
                "weight": weight,
                "prefix": cfg["prefix"],
                "total_asset": slot_total_asset,
                "stock_value": slot_stock_val,
                "cash_balance": slot_cash
            }

        # 4. 실시간 가상 스캐너 시그널 맵 모사
        all_signals = []
        for ticker in tickers_list:
            if ticker not in current_prices:
                continue
            row = base_sim.processed_metrics[ticker].loc[t]
            all_signals.append({
                "ticker": ticker,
                "price": current_prices[ticker],
                "details": row.to_dict()
            })

        # ------------------ (Part A) 보유 종목 실시간 감시 및 매도 주문 ------------------
        holdings_to_check = list(holdings)
        for h in holdings_to_check:
            slot_key = h.strategy_type
            clean_ticker = h.ticker
            
            if slot_key not in strategies:
                continue
                
            strategy_instance = strategies[slot_key]
            
            if clean_ticker not in current_prices:
                continue
                
            current_price = current_prices[clean_ticker]
            row = base_sim.processed_metrics[clean_ticker].loc[t]
            
            # 최고가 갱신
            if current_price > h.highest_price:
                h.highest_price = current_price
                
            profit_rate = ((current_price - h.avg_price) / h.avg_price) * 100
            
            current_score = strategy_instance.calculate_score(row, sentiment, is_entry=False)
            is_smart_exit = row.get('is_smart_exit', 0.0) == 1.0

            # ATR 동적 익절/손절선 계산
            atr = row.get('ATR', 0.0)
            stop_loss_pct = strategy_instance.get_stop_loss_pct(atr, current_price)
            trailing_stop_pct = strategy_instance.get_trailing_stop_pct(atr, current_price)

            sell_reason = None
            is_breached = False
            breach_reason = ""
            
            if profit_rate <= -stop_loss_pct:
                is_breached = True
                breach_reason = f"동적 손절선 이탈 (-{stop_loss_pct:.2f}% 돌파 | 수익률: {profit_rate:.2f}%)"
            elif current_price <= h.highest_price * (1 - trailing_stop_pct / 100) and h.highest_price > h.avg_price:
                is_breached = True
                breach_reason = f"동적 트레일링 스탑 이탈 (-{trailing_stop_pct:.2f}% 돌파 | 수익률: {profit_rate:.2f}%)"
            
            cooldown_key = (h.ticker, h.strategy_type)
            if is_breached:
                breach_counts[cooldown_key] = breach_counts.get(cooldown_key, 0) + 1
                if breach_counts[cooldown_key] >= 2:
                    sell_reason = breach_reason + " [2회 연속 이탈 확정]"
            else:
                breach_counts.pop(cooldown_key, None)
                
            if not sell_reason and profit_rate >= strategy_instance.min_smart_exit_profit and is_smart_exit:
                sell_reason = f"스마트 조기 익절 (RSI-MACD 조건 충족 | 수익률: {profit_rate:.2f}%)"
            elif not sell_reason and strategy_instance.is_signal_collapsed(current_score, sentiment):
                sell_reason = f"강세 시그널 붕괴 ({current_score}점 도달)"

            if sell_reason:
                # 매도 청산 집행
                sell_qty = h.quantity
                revenue = sell_qty * current_price
                sell_fee = revenue * 0.0007 # 0.07% 수수료
                sec_fee = revenue * 0.0000278 # SEC Fee
                net_revenue = revenue - sell_fee - sec_fee
                
                cash_balance += net_revenue
                
                # 매입 평단금 계산
                buy_gross = h.avg_price * sell_qty
                buy_fee = buy_gross * 0.0007
                
                realized_pnl = net_revenue - (buy_gross + buy_fee)
                calc_return_rate = (realized_pnl / buy_gross) * 100 if buy_gross > 0 else 0.0
                
                trade_logs.append({
                    "timestamp": t.strftime('%Y-%m-%d %H:%M:%S') if hasattr(t, 'strftime') else str(t),
                    "ticker": h.ticker,
                    "trade_type": "SELL",
                    "price": current_price,
                    "quantity": sell_qty,
                    "realized_pnl": realized_pnl,
                    "return_rate": calc_return_rate,
                    "reason": sell_reason,
                    "strategy_type": h.strategy_type
                })
                
                sell_cooldowns[cooldown_key] = t
                holdings.remove(h)
                breach_counts.pop(cooldown_key, None)

        # ------------------ (Part B) 슬롯별 신규 매수 기회 검사 및 분할 매수 ------------------
        # Focusing 필터 적용 (RVOL >= 2.0 대량 수급 매집봉 5~10개 압축 선별)
        candidates_focus = []
        for s in all_signals:
            ticker = s["ticker"]
            details = s["details"]
            rvol = details.get("RVOL", 0.0)
            has_accumulation = rvol >= 2.0 or details.get("premarket_gap_pct", 0.0) >= 3.0
            is_safe = details.get("risk", "LOW") != "HIGH"
            if has_accumulation and is_safe:
                score_weight = rvol * 10 + details.get("rs", 0.0)
                candidates_focus.append((ticker, score_weight))
                
        candidates_focus.sort(key=lambda x: x[1], reverse=True)
        focused_tickers = {t for t, _ in candidates_focus[:10]}
        
        if len(focused_tickers) < 5:
            additional_needed = 5 - len(focused_tickers)
            for tk in tickers_list:
                if tk not in focused_tickers:
                     focused_tickers.add(tk)
                     additional_needed -= 1
                     if additional_needed <= 0:
                         break

        for slot_key, slot_info in slot_allocations.items():
            if slot_key == "regime_switching" and sentiment != "BULLISH":
                continue

            strategy_instance = strategies[slot_key]
            slot_cash_usd = slot_info["cash_balance"]
            slot_total_asset_usd = slot_info["total_asset"]
            
            # 슬롯별 최대 3종목 가드
            slot_holdings_count = sum(1 for x in holdings if x.strategy_type == slot_key)
            if slot_holdings_count >= 3:
                continue
                
            cutoff_score = strategy_instance.get_cutoff_score(sentiment)

            for s in all_signals:
                clean_ticker = s['ticker']
                
                # Focusing 필터에 포함된 최정예 종목만 자금 배정
                if clean_ticker not in focused_tickers:
                    continue
                    
                row = s['details']
                score = strategy_instance.calculate_score(row, sentiment, is_entry=True)
                
                if score >= cutoff_score:
                    existing_holding = next((x for x in holdings if x.ticker == clean_ticker and x.strategy_type == slot_key), None)
                    
                    proposed_alloc_factor = 1.0
                    next_stage = 3
                    
                    if existing_holding:
                        pyramid_trigger_1 = strategy_instance.get_pyramid_trigger(1)
                        if pyramid_trigger_1 > 100.0 or sentiment != "BULLISH":
                            continue
                            
                        buy_stage = existing_holding.buy_stage
                        current_price = s['price']
                        profit_rate = ((current_price - existing_holding.avg_price) / existing_holding.avg_price) * 100
                        pyramid_trigger_2 = strategy_instance.get_pyramid_trigger(2)

                        if buy_stage == 1:
                            if profit_rate >= pyramid_trigger_1:
                                proposed_alloc_factor = 0.35
                                next_stage = 2
                            else:
                                continue
                        elif buy_stage == 2:
                            if profit_rate >= pyramid_trigger_2:
                                proposed_alloc_factor = 0.50
                                next_stage = 3
                            else:
                                continue
                        else:
                            continue
                    else:
                        proposed_alloc_factor = strategy_instance.get_initial_entry_factor(sentiment)
                        if sentiment == "BULLISH" and proposed_alloc_factor < 1.0:
                            next_stage = 1
                        else:
                            next_stage = 3

                    # Whipsaw 방지 쿨다운 검사
                    cooldown_key = (clean_ticker, slot_key)
                    last_sell = sell_cooldowns.get(cooldown_key)
                    if last_sell:
                        cooldown_hours = 2.0
                        time_diff = (pd.to_datetime(t) - pd.to_datetime(last_sell)).total_seconds() / 3600.0
                        if time_diff < cooldown_hours:
                            continue

                    current_price = s['price']
                    
                    if slot_cash_usd < 50.0:
                        continue

                    base_alloc_usd = slot_total_asset_usd * strategy_instance.base_allocation_pct
                    if strategy_instance.min_allocation_usd > 0.0:
                        base_alloc_usd = max(strategy_instance.min_allocation_usd, base_alloc_usd)

                    atr = row.get('ATR', 0.0)
                    vol_factor = 1.0
                    if atr > 0:
                        atr_pct = (atr / current_price) * 100
                        if atr_pct > 0:
                            vol_factor = max(0.5, min(1.5, 2.0 / atr_pct))
                    
                    score_factor = 1.0 + (score - cutoff_score) * 0.05
                    proposed_value_usd = base_alloc_usd * vol_factor * score_factor * proposed_alloc_factor
                    
                    max_order_budget_usd = slot_cash_usd * 0.95
                    final_qty = int(min(proposed_value_usd / current_price, max_order_budget_usd / current_price))
                    
                    if final_qty == 0 and max_order_budget_usd >= current_price:
                        final_qty = 1
                        
                    if final_qty >= 1:
                        # 매수 집행 및 수수료 정산
                        cost = final_qty * current_price
                        buy_fee = cost * 0.0007
                        total_cost = cost + buy_fee
                        
                        cash_balance -= total_cost
                        slot_cash_usd -= total_cost
                        
                        if existing_holding:
                            old_qty = existing_holding.quantity
                            old_avg = existing_holding.avg_price
                            new_qty = old_qty + final_qty
                            new_avg = ((old_avg * old_qty) + (current_price * final_qty)) / new_qty
                            
                            existing_holding.avg_price = round(new_avg, 4)
                            existing_holding.quantity = new_qty
                            existing_holding.buy_stage = next_stage
                            existing_holding.highest_price = max(existing_holding.highest_price, current_price)
                        else:
                            holdings.append(MockHolding(
                                ticker=clean_ticker,
                                ticker_name=clean_ticker,
                                avg_price=current_price,
                                quantity=final_qty,
                                highest_price=current_price,
                                regime_mode=sentiment,
                                buy_stage=next_stage,
                                strategy_type=slot_key
                            ))
                            
                        # BUY 로그 기록
                        trade_logs.append({
                            "timestamp": t.strftime('%Y-%m-%d %H:%M:%S') if hasattr(t, 'strftime') else str(t),
                            "ticker": clean_ticker,
                            "trade_type": "BUY",
                            "price": current_price,
                            "quantity": final_qty,
                            "realized_pnl": 0.0,
                            "return_rate": 0.0,
                            "reason": f"Stage {next_stage} Entry/Add",
                            "strategy_type": slot_key
                        })

    # 시뮬레이션 통계 지표 연산
    final_stock_value = sum(h.quantity * h.current_price for h in holdings)
    final_value = cash_balance + final_stock_value
    total_return = (final_value - initial_cash) / initial_cash * 100
    
    # MDD 계산
    df_equity = pd.DataFrame(equity_curve)
    df_equity['peak'] = df_equity['total'].cummax()
    df_equity['drawdown'] = (df_equity['total'] - df_equity['peak']) / df_equity['peak'] * 100
    mdd = df_equity['drawdown'].min()
    
    # 승률 계산
    sell_trades = [x for x in trade_logs if x["trade_type"] == "SELL"]
    total_trades = len(sell_trades)
    winning_trades = [x for x in sell_trades if x["realized_pnl"] > 0]
    win_rate = (len(winning_trades) / len(sell_trades) * 100) if sell_trades else 0.0
    total_pnl = final_value - initial_cash
    
    # 종목별 거래 횟수 통계
    stats = {}
    for log in trade_logs:
        ticker = log["ticker"]
        t_type = log["trade_type"]
        pnl = log["realized_pnl"]
        
        clean_t = ticker
        
        if clean_t not in stats:
            stats[clean_t] = {"buys": 0, "sells": 0, "pnl": 0.0}
            
        if t_type == "BUY":
            stats[clean_t]["buys"] += 1
        elif t_type == "SELL":
            stats[clean_t]["sells"] += 1
            stats[clean_t]["pnl"] += pnl
            
    # Chart friendly equity curve data (every 24 timestamps to reduce network footprint)
    chart_equity = equity_curve[::24]
    if len(equity_curve) > 0 and chart_equity[-1] != equity_curve[-1]:
        chart_equity.append(equity_curve[-1])
            
    return {
        "final_value": final_value,
        "total_return_rate": total_return,
        "total_pnl": total_pnl,
        "mdd": mdd,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "ticker_stats": stats,
        "equity_curve": chart_equity,
        **calculate_performance_metrics(equity_curve, initial_value=initial_cash),
    }
 
def get_dynamic_tickers_list(tickers_list: List[str] = None, db = None) -> List[str]:
    if not tickers_list and db:
        try:
            from app.core.models import WatchList, Holding, TradeLog
            watch_tickers = [w.ticker for w in db.query(WatchList.ticker).all() if w.ticker]
            holding_tickers = [h.ticker for h in db.query(Holding.ticker).all() if h.ticker]
            trade_tickers = [t.ticker for t in db.query(TradeLog.ticker).all() if t.ticker]
            
            raw_tickers = set(watch_tickers + holding_tickers + trade_tickers)
            clean_tickers = {t.strip().upper() for t in raw_tickers if t}
            tickers_list = list(clean_tickers)
            logger.info(f"[Backtest Tournament] Dynamically extracted {len(tickers_list)} tickers from Watchlist, Holdings, and TradeLogs: {tickers_list}")
        except Exception as e:
            logger.error(f"[Backtest Tournament] Failed to extract tickers dynamically: {e}", exc_info=True)
    return tickers_list

def check_tournament_cache(start_date: str, end_date: str, tickers_list: List[str] = None) -> dict | None:
    cache_path = _build_tournament_cache_path(start_date, end_date, tickers_list)
    if cache_path.exists():
        try:
            with cache_path.open("r", encoding="utf-8") as f_c:
                return _apply_strategy_display_names(json.load(f_c))
        except Exception as e:
            logger.warning(f"Cache loading failed, falling back to live calc: {e}")
    return None

async def run_dynamic_tournament_task(start_date: str, end_date: str, tickers_list: List[str], lock_path: Path):
    try:
        # Create lock
        lock_path.touch(exist_ok=True)
        results = await _run_dynamic_tournament_internal(start_date, end_date, tickers_list)
        return results
    except Exception as e:
        logger.error(f"Error in background tournament: {e}", exc_info=True)
    finally:
        if lock_path.exists():
            lock_path.unlink()

async def run_dynamic_tournament(start_date: str, end_date: str, tickers_list: List[str] = None, db = None) -> List[Dict[str, Any]]:
    # Legacy wrapper if someone calls it directly
    tickers_list = get_dynamic_tickers_list(tickers_list, db)
    cached = check_tournament_cache(start_date, end_date, tickers_list)
    if cached: return cached
    return await _run_dynamic_tournament_internal(start_date, end_date, tickers_list)

async def _run_dynamic_tournament_internal(start_date: str, end_date: str, tickers_list: List[str] = None) -> List[Dict[str, Any]]:
    """과거 지정된 특정 기간(start_date ~ end_date) 동안 5대 전략 토너먼트 배틀을 실행하고 그 통계와 자산 곡선을 캐시/반환합니다."""
            
    if not tickers_list:
        from app.scanner.discovery import get_seed_tickers
        tickers_list, _ = await get_seed_tickers()
        if not tickers_list:
            tickers_list = ["NVDA", "AAPL", "MSFT", "TSLA", "AMD"]
    interval = "1h"
    cash = 10000.0

    # 1. 공통 yfinance 데이터 로드
    base_sim = BacktestSimulator(
        tickers=tickers_list,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        initial_cash=cash,
        strategy_type="regime_switching"
    )
    await base_sim.prepare_data()

    results = []

    # ------------------ [참가자 1: 에피소딕피벗 C 표준형] ------------------
    sim_ep_c = BacktestSimulator(
        tickers=tickers_list,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        initial_cash=cash,
        strategy_type="strategy_c_ep"
    )
    sim_ep_c.processed_metrics = base_sim.processed_metrics
    sim_ep_c.qqq_metrics = base_sim.qqq_metrics
    sim_ep_c.timeline = base_sim.timeline
    sim_ep_c.tickers_data = base_sim.tickers_data
    
    report_ep_c = sim_ep_c.run()
    
    stats_ep_c = {}
    for log in sim_ep_c.broker.trade_logs:
        ticker = log["ticker"]
        t_type = log["trade_type"]
        pnl = log["realized_pnl"]
        if ticker not in stats_ep_c:
            stats_ep_c[ticker] = {"buys": 0, "sells": 0, "pnl": 0.0}
        if t_type == "BUY":
            stats_ep_c[ticker]["buys"] += 1
        elif t_type == "SELL":
            stats_ep_c[ticker]["sells"] += 1
            stats_ep_c[ticker]["pnl"] += pnl
            
    # Chart format
    curve_ep_c = [{"timestamp": e["timestamp"].strftime('%Y-%m-%d %H:%M:%S') if hasattr(e["timestamp"], 'strftime') else str(e["timestamp"]), "total": e["total"]} for e in sim_ep_c.broker.equity_curve[::24]]
            
    results.append({
        "strategy_type": "strategy_c_ep",
        "name": Translator.translate_strategy("strategy_c_ep", "ko"),
        "final_value": report_ep_c["final_value"],
        "total_pnl": report_ep_c["total_pnl"],
        "total_return_rate": report_ep_c["total_return_rate"],
        "mdd": report_ep_c["mdd"],
        "total_trades": report_ep_c["total_trades"],
        "win_rate": report_ep_c["win_rate"],
        "ticker_stats": stats_ep_c,
        "equity_curve": curve_ep_c
    })

    # ------------------ [참가자 2: 시니어 단순화] ------------------
    sim_senior = BacktestSimulator(
        tickers=tickers_list,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        initial_cash=cash,
        strategy_type="senior_simple"
    )
    sim_senior.processed_metrics = base_sim.processed_metrics
    sim_senior.qqq_metrics = base_sim.qqq_metrics
    sim_senior.timeline = base_sim.timeline
    sim_senior.tickers_data = base_sim.tickers_data
    
    report_senior = sim_senior.run()
    
    stats_senior = {}
    for log in sim_senior.broker.trade_logs:
        ticker = log["ticker"]
        t_type = log["trade_type"]
        pnl = log["realized_pnl"]
        if ticker not in stats_senior:
            stats_senior[ticker] = {"buys": 0, "sells": 0, "pnl": 0.0}
        if t_type == "BUY":
            stats_senior[ticker]["buys"] += 1
        elif t_type == "SELL":
            stats_senior[ticker]["sells"] += 1
            stats_senior[ticker]["pnl"] += pnl
            
    curve_senior = [{"timestamp": e["timestamp"].strftime('%Y-%m-%d %H:%M:%S') if hasattr(e["timestamp"], 'strftime') else str(e["timestamp"]), "total": e["total"]} for e in sim_senior.broker.equity_curve[::24]]
            
    results.append({
        "strategy_type": "senior_simple",
        "name": Translator.translate_strategy("senior_simple", "ko"),
        "final_value": report_senior["final_value"],
        "total_pnl": report_senior["total_pnl"],
        "total_return_rate": report_senior["total_return_rate"],
        "mdd": report_senior["mdd"],
        "total_trades": report_senior["total_trades"],
        "win_rate": report_senior["win_rate"],
        "ticker_stats": stats_senior,
        "equity_curve": curve_senior
    })

    # ------------------ [참가자 3: 마스터 레짐스위칭] ------------------
    sim_master = BacktestSimulator(
        tickers=tickers_list,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        initial_cash=cash,
        strategy_type="regime_switching"
    )
    sim_master.processed_metrics = base_sim.processed_metrics
    sim_master.qqq_metrics = base_sim.qqq_metrics
    sim_master.timeline = base_sim.timeline
    sim_master.tickers_data = base_sim.tickers_data
    
    report_master = sim_master.run()
    
    stats_master = {}
    for log in sim_master.broker.trade_logs:
        ticker = log["ticker"]
        t_type = log["trade_type"]
        pnl = log["realized_pnl"]
        if ticker not in stats_master:
            stats_master[ticker] = {"buys": 0, "sells": 0, "pnl": 0.0}
        if t_type == "BUY":
            stats_master[ticker]["buys"] += 1
        elif t_type == "SELL":
            stats_master[ticker]["sells"] += 1
            stats_master[ticker]["pnl"] += pnl
            
    curve_master = [{"timestamp": e["timestamp"].strftime('%Y-%m-%d %H:%M:%S') if hasattr(e["timestamp"], 'strftime') else str(e["timestamp"]), "total": e["total"]} for e in sim_master.broker.equity_curve[::24]]
            
    results.append({
        "strategy_type": "regime_switching",
        "name": Translator.translate_strategy("regime_switching", "ko"),
        "final_value": report_master["final_value"],
        "total_pnl": report_master["total_pnl"],
        "total_return_rate": report_master["total_return_rate"],
        "mdd": report_master["mdd"],
        "total_trades": report_master["total_trades"],
        "win_rate": report_master["win_rate"],
        "ticker_stats": stats_master,
        "equity_curve": curve_master
    })

    # ------------------ [참가자 4: 격리형 3슬롯 (이전)] ------------------
    slots_config_3 = {
        "episodic_pivot": {
            "weight_bullish": 1.0,
            "weight_bearish": 0.30,
            "prefix": "EP_",
            "strategy_key": "episodic_pivot"
        },
        "asqs": {
            "weight_bullish": 1.0,
            "weight_bearish": 0.15,
            "prefix": "ASQS_",
            "strategy_key": "asqs"
        },
        "regime_switching": {
            "weight_bullish": 1.0,
            "weight_bearish": 0.0,
            "prefix": "RS_",
            "strategy_key": "regime_switching"
        }
    }
    report_3slot = run_multi_strategy_sim(base_sim, slots_config_3, cash, tickers_list)
    curve_3slot = [{"timestamp": e["timestamp"], "total": e["total"]} for e in report_3slot["equity_curve"]]
    
    results.append({
        "strategy_type": "multi_slot_3",
        "name": Translator.translate_strategy("multi_slot_3", "ko"),
        "final_value": report_3slot["final_value"],
        "total_pnl": report_3slot["total_pnl"],
        "total_return_rate": report_3slot["total_return_rate"],
        "mdd": report_3slot["mdd"],
        "total_trades": report_3slot["total_trades"],
        "win_rate": report_3slot["win_rate"],
        "ticker_stats": report_3slot["ticker_stats"],
        "equity_curve": curve_3slot
    })

    # ------------------ [참가자 5: 격리형 2슬롯 (현재)] ------------------
    slots_config_2 = {
        "episodic_pivot": {
            "weight_bullish": 1.0,
            "weight_bearish": 0.50,
            "prefix": "EP_",
            "strategy_key": "episodic_pivot"
        },
        "regime_switching": {
            "weight_bullish": 1.0,
            "weight_bearish": 0.0,
            "prefix": "RS_",
            "strategy_key": "regime_switching"
        }
    }
    report_2slot = run_multi_strategy_sim(base_sim, slots_config_2, cash, tickers_list)
    curve_2slot = [{"timestamp": e["timestamp"], "total": e["total"]} for e in report_2slot["equity_curve"]]
    
    results.append({
        "strategy_type": "multi_slot",
        "name": Translator.translate_strategy("multi_slot", "ko"),
        "final_value": report_2slot["final_value"],
        "total_pnl": report_2slot["total_pnl"],
        "total_return_rate": report_2slot["total_return_rate"],
        "mdd": report_2slot["mdd"],
        "total_trades": report_2slot["total_trades"],
        "win_rate": report_2slot["win_rate"],
        "ticker_stats": report_2slot["ticker_stats"],
        "equity_curve": curve_2slot
    })

    # ------------------ [참가자 6: 프리마켓 고점 돌파] ------------------
    sim_pb = BacktestSimulator(
        tickers=tickers_list,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        initial_cash=cash,
        strategy_type="premarket_breakout"
    )
    sim_pb.processed_metrics = base_sim.processed_metrics
    sim_pb.qqq_metrics = base_sim.qqq_metrics
    sim_pb.timeline = base_sim.timeline
    sim_pb.tickers_data = base_sim.tickers_data
    
    report_pb = sim_pb.run()
    
    stats_pb = {}
    for log in sim_pb.broker.trade_logs:
        ticker = log["ticker"]
        t_type = log["trade_type"]
        pnl = log["realized_pnl"]
        if ticker not in stats_pb:
            stats_pb[ticker] = {"buys": 0, "sells": 0, "pnl": 0.0}
        if t_type == "BUY":
            stats_pb[ticker]["buys"] += 1
        elif t_type == "SELL":
            stats_pb[ticker]["sells"] += 1
            stats_pb[ticker]["pnl"] += pnl
            
    curve_pb = [{"timestamp": e["timestamp"].strftime('%Y-%m-%d %H:%M:%S') if hasattr(e["timestamp"], 'strftime') else str(e["timestamp"]), "total": e["total"]} for e in sim_pb.broker.equity_curve[::24]]
            
    results.append({
        "strategy_type": "premarket_breakout",
        "name": Translator.translate_strategy("premarket_breakout", "ko"),
        "final_value": report_pb["final_value"],
        "total_pnl": report_pb["total_pnl"],
        "total_return_rate": report_pb["total_return_rate"],
        "mdd": report_pb["mdd"],
        "total_trades": report_pb["total_trades"],
        "win_rate": report_pb["win_rate"],
        "ticker_stats": stats_pb,
        "equity_curve": curve_pb
    })

    # ------------------ [참가자 7: 추세 안정화 눌림목] ------------------
    sim_ts = BacktestSimulator(
        tickers=tickers_list,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        initial_cash=cash,
        strategy_type="trend_stabilization"
    )
    sim_ts.processed_metrics = base_sim.processed_metrics
    sim_ts.qqq_metrics = base_sim.qqq_metrics
    sim_ts.timeline = base_sim.timeline
    sim_ts.tickers_data = base_sim.tickers_data
    
    report_ts = sim_ts.run()
    
    stats_ts = {}
    for log in sim_ts.broker.trade_logs:
        ticker = log["ticker"]
        t_type = log["trade_type"]
        pnl = log["realized_pnl"]
        if ticker not in stats_ts:
            stats_ts[ticker] = {"buys": 0, "sells": 0, "pnl": 0.0}
        if t_type == "BUY":
            stats_ts[ticker]["buys"] += 1
        elif t_type == "SELL":
            stats_ts[ticker]["sells"] += 1
            stats_ts[ticker]["pnl"] += pnl
            
    curve_ts = [{"timestamp": e["timestamp"].strftime('%Y-%m-%d %H:%M:%S') if hasattr(e["timestamp"], 'strftime') else str(e["timestamp"]), "total": e["total"]} for e in sim_ts.broker.equity_curve[::24]]
            
    results.append({
        "strategy_type": "trend_stabilization",
        "name": Translator.translate_strategy("trend_stabilization", "ko"),
        "final_value": report_ts["final_value"],
        "total_pnl": report_ts["total_pnl"],
        "total_return_rate": report_ts["total_return_rate"],
        "mdd": report_ts["mdd"],
        "total_trades": report_ts["total_trades"],
        "win_rate": report_ts["win_rate"],
        "ticker_stats": stats_ts,
        "equity_curve": curve_ts
    })

    report_lookup = {
        "strategy_c_ep": report_ep_c,
        "senior_simple": report_senior,
        "regime_switching": report_master,
        "multi_slot_3": report_3slot,
        "multi_slot": report_2slot,
        "premarket_breakout": report_pb,
        "trend_stabilization": report_ts,
    }
    qqq_initial = float(base_sim.qqq_metrics["Close"].iloc[0])
    qqq_final = float(base_sim.qqq_metrics["Close"].iloc[-1])
    qqq_return = (qqq_final / qqq_initial - 1.0) * 100.0

    for result in results:
        source_report = report_lookup[result["strategy_type"]]
        for metric_name in (
            "annualized_return",
            "annualized_volatility",
            "sharpe_ratio",
            "sortino_ratio",
            "calmar_ratio",
            "mdd_recovery_days",
            "mdd_recovered",
            "max_underwater_days",
            "observation_days",
        ):
            result[metric_name] = source_report.get(metric_name, 0.0)
        result["qqq_bench_return_rate"] = round(qqq_return, 2)
        result.update(
            assess_strategy_report(
                result["strategy_type"],
                result,
                minimum_trades=15,
            )
        )

    results.sort(
        key=lambda result: (
            result["selection_eligible"],
            result["selection_score"],
        ),
        reverse=True,
    )

    # 캐시 저장
    try:
        with cache_path.open("w", encoding="utf-8") as f_w:
            json.dump(results, f_w, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save tournament cache: {e}")
        
    return _apply_strategy_display_names(results)
