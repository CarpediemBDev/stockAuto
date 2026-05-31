import pandas as pd
import numpy as np
import asyncio
from datetime import datetime
from app.scanner.data_provider import fetch_ohlcv, fetch_bulk_ohlcv
from app.scanner.indicators import (
    calculate_ema, calculate_rsi, calculate_macd, calculate_atr, 
    calculate_obv_divergence, calculate_rsi_bb, calculate_vwap, calculate_wick_ratio
)
from app.core.logging import logger

from app.core.config import settings

class BacktestBroker:
    """
    가상의 시간축 위에서 자산 잔고, 가상 포지션, 체결 로그를 기록하고 시뮬레이션하는 백테스트 전용 브로커.
    KISBroker 및 SimulatedBroker의 인터페이스 규격을 보존하여 상위 전략 로직과의 호환성을 극대화합니다.
    """
    def __init__(self, initial_cash_usd: float = 10000.0):
        self.initial_cash = initial_cash_usd
        self.cash = initial_cash_usd
        self.portfolio_value = initial_cash_usd
        self.holdings = {}  # {ticker: {"quantity": int, "avg_price": float, "highest_price": float, "buy_stage": int, "ticker_name": str}}
        self.trade_logs = []  # 리스트 of dicts
        self.equity_curve = []  # 리스트 of dicts: {"timestamp": datetime, "cash": float, "holdings_value": float, "total": float}
        self.sell_cooldowns = {}  # {ticker: last_sell_timestamp}

    def get_account_balance(self, current_prices: dict) -> dict:
        holdings_value = sum(h["quantity"] * current_prices.get(ticker, h["avg_price"]) for ticker, h in self.holdings.items())
        total_asset = self.cash + holdings_value
        profit_loss = total_asset - self.initial_cash
        profit_rate = (profit_loss / self.initial_cash) * 100
        return {
            "total_asset": total_asset,
            "cash_balance": self.cash,
            "stock_balance": holdings_value,
            "profit_loss": profit_loss,
            "profit_rate": round(profit_rate, 2),
            "is_mock": True,
            "provider": "Backtest"
        }

    def buy_order(self, ticker: str, quantity: int, price: float, buy_stage: int, timestamp: datetime, ticker_name: str = "") -> dict:
        """가상 매수 주문 집행 및 KIS 매수 수수료가 적용된 평단가 가중평균 시뮬레이션"""
        cost = quantity * price
        buy_fee = cost * settings.KIS_FEE_RATE
        total_cost = cost + buy_fee
        
        if self.cash < total_cost:
            # 잔고 안전장치: 남은 예수금 내에서 수수료까지 감안하여 최대한 매매 시도
            max_qty = int(self.cash / (price * (1 + settings.KIS_FEE_RATE)))
            if max_qty >= 1:
                quantity = max_qty
                cost = quantity * price
                buy_fee = cost * settings.KIS_FEE_RATE
                total_cost = cost + buy_fee
            else:
                return {"success": False, "message": "Insufficient cash for backtest buy order."}

        self.cash -= total_cost
        
        if ticker in self.holdings:
            # 💡 피라미딩 추가 매수 (불타기)
            h = self.holdings[ticker]
            old_qty = h["quantity"]
            old_avg = h["avg_price"]
            
            new_qty = old_qty + quantity
            new_avg = ((old_avg * old_qty) + (price * quantity)) / new_qty
            
            self.holdings[ticker] = {
                "quantity": new_qty,
                "avg_price": round(new_avg, 4),
                "highest_price": max(h["highest_price"], price),
                "buy_stage": buy_stage,
                "ticker_name": ticker_name or h["ticker_name"]
            }
        else:
            # 💡 신규 포지션 진입
            self.holdings[ticker] = {
                "quantity": quantity,
                "avg_price": price,
                "highest_price": price,
                "buy_stage": buy_stage,
                "ticker_name": ticker_name or ticker
            }

        order_no = f"BT-BUY-{timestamp.strftime('%Y%m%d%H%M%S')}"
        self.trade_logs.append({
            "timestamp": timestamp,
            "ticker": ticker,
            "ticker_name": ticker_name or ticker,
            "trade_type": "BUY",
            "price": price,
            "quantity": quantity,
            "order_no": order_no,
            "buy_stage": buy_stage,
            "realized_pnl": 0.0,
            "return_rate": 0.0,
            "reason": f"Stage {buy_stage} Entry/Add-on"
        })
        return {"success": True, "order_no": order_no, "filled_qty": quantity, "filled_price": price}

    def sell_order(self, ticker: str, quantity: int, price: float, reason: str, timestamp: datetime) -> dict:
        """가상 매도 주문 집행 및 KIS 매도 수수료 및 SEC Fee가 정밀 차감된 실수익(Net) 기록"""
        if ticker not in self.holdings:
            return {"success": False, "message": f"Ticker {ticker} not in holdings."}

        h = self.holdings[ticker]
        sell_qty = min(quantity, h["quantity"])
        revenue = sell_qty * price
        
        # 매도 시 제비용 차감
        sell_fee = revenue * settings.KIS_FEE_RATE
        sec_fee = revenue * settings.SEC_FEE_RATE
        net_revenue = revenue - sell_fee - sec_fee
        
        self.cash += net_revenue
        
        # 총 매입 금액 및 매수 시 수수료 계산
        buy_gross = h["avg_price"] * sell_qty
        buy_fee = buy_gross * settings.KIS_FEE_RATE
        
        # 최종 실수익 (Net realized PnL) = 매도 정산금 - (매수 금액 + 매수 시 수수료)
        realized_pnl = net_revenue - (buy_gross + buy_fee)
        return_rate = (realized_pnl / buy_gross) * 100 if buy_gross > 0 else 0.0
        
        order_no = f"BT-SELL-{timestamp.strftime('%Y%m%d%H%M%S')}"
        self.trade_logs.append({
            "timestamp": timestamp,
            "ticker": ticker,
            "ticker_name": h["ticker_name"],
            "trade_type": "SELL",
            "price": price,
            "quantity": sell_qty,
            "order_no": order_no,
            "buy_stage": h["buy_stage"],
            "realized_pnl": round(realized_pnl, 2),
            "return_rate": round(return_rate, 2),
            "reason": reason
        })

        # 쿨다운용 기록 보관
        self.sell_cooldowns[ticker] = timestamp

        if sell_qty >= h["quantity"]:
            del self.holdings[ticker]
        else:
            self.holdings[ticker]["quantity"] -= sell_qty

        return {"success": True, "order_no": order_no, "filled_qty": sell_qty, "filled_price": price}

    def update_equity(self, timestamp: datetime, current_prices: dict):
        holdings_value = sum(h["quantity"] * current_prices.get(ticker, h["avg_price"]) for ticker, h in self.holdings.items())
        total = self.cash + holdings_value
        self.portfolio_value = total
        self.equity_curve.append({
            "timestamp": timestamp,
            "cash": round(self.cash, 2),
            "holdings_value": round(holdings_value, 2),
            "total": round(total, 2)
        })


class BacktestSimulator:
    """
    과거 역사적 데이터를 로드하여 StockAuto v2.0 트레이딩 규칙과 자금 관리 모듈을 정밀 시뮬레이션하는 엔진.
    데이터 프로바이더를 연동하며 미래 데이터를 참조하지 않는 완벽한 Event-driven 방식으로 작동합니다.
    """
    def __init__(self, tickers: list, start_date: str, end_date: str, interval: str = "1h", initial_cash: float = 10000.0, csv_path: str = None, strategy_type: str = "complex"):
        self.tickers = list(set(tickers))
        self.start_date = start_date
        self.end_date = end_date
        self.interval = interval
        self.csv_path = csv_path
        self.broker = BacktestBroker(initial_cash)
        self.strategy_type = strategy_type
        
        # 💡 [전략 패턴] 전략 팩토리를 통해 해당 전략 객체 로드 및 장착
        from app.strategies.strategy_factory import get_strategy
        self.strategy = get_strategy(strategy_type)
        
        # 💡 이탈 연속 횟수 추적 캐시 (2회 연속 이탈 확정용)
        self.breach_counts = {}  # {ticker: count}
        
        # 다운로드된 원시 데이터들 저장소
        self.tickers_data = {}  # {ticker: DataFrame}
        self.qqq_data = None  # QQQ DataFrame
        
        # 미리 계산된 지표 시계열 데이터 저장소 (시뮬레이션 가속화용)
        self.processed_metrics = {}  # {ticker: DataFrame}
        self.qqq_metrics = None  # DataFrame containing QQQ indicators
        self.timeline = []  # 정렬된 공통 시계열 타임스탬프 리스트

    async def prepare_data(self):
        """QQQ 및 대상 티커들의 데이터를 다운로드하고 모든 기술적 지표를 벡터화 사전 연산하여 타임라인을 구축합니다."""
        logger.info(f"[Backtest prepare_data] Sourcing data from {self.start_date} to {self.end_date} (Interval: {self.interval})")
        
        # 1. QQQ 지수 데이터 수집 (레짐 스위칭용)
        # 1시간봉/일봉 백테스트 시에는 동일 인터벌을 적용하고, 1분봉 정밀 시에는 1분봉 QQQ 데이터와 15분봉 QQQ 데이터를 적절히 조화시킵니다.
        # 여기서는 주 인터벌 데이터를 기준으로 정합합니다.
        period_diff = (datetime.strptime(self.end_date, "%Y-%m-%d") - datetime.strptime(self.start_date, "%Y-%m-%d")).days
        period_str = f"{period_diff + 5}d"  # 주말 마진 추가
        
        # 1분봉은 최대 30일 제한이 있으므로 안전하게 period를 제한
        if self.interval == "1m":
            period_str = "30d"
            logger.warning("[Backtest] Interval 1m selected. Restricting range to maximum 30 days due to yfinance limit.")

        logger.info(f"[Backtest] Fetching QQQ index data...")
        self.qqq_data = await fetch_ohlcv("QQQ", interval=self.interval, period=period_str)
        if self.qqq_data.empty:
            raise Exception("Failed to fetch QQQ index data. Backtesting cannot proceed without regime guide.")
        
        # 시간 범위 필터 적용
        self.qqq_data = self.qqq_data[(self.qqq_data.index >= self.start_date) & (self.qqq_data.index <= self.end_date)]
        
        # QQQ 지표 계산 (MA20, MA50)
        self.qqq_metrics = pd.DataFrame(index=self.qqq_data.index)
        self.qqq_metrics['Close'] = self.qqq_data['Close']
        self.qqq_metrics['MA20'] = calculate_ema(self.qqq_data['Close'], 20)
        self.qqq_metrics['MA50'] = calculate_ema(self.qqq_data['Close'], 50)
        
        # QQQ 레짐 모드 판단 열 추가
        regimes = []
        for i in range(len(self.qqq_metrics)):
            close = self.qqq_metrics['Close'].iloc[i]
            ma20 = self.qqq_metrics['MA20'].iloc[i]
            ma50 = self.qqq_metrics['MA50'].iloc[i]
            if pd.isna(ma20) or pd.isna(ma50):
                regimes.append("NEUTRAL")
            elif close > ma20 and ma20 > ma50:
                regimes.append("BULLISH")
            elif close < ma20:
                regimes.append("BEARISH")
            else:
                regimes.append("NEUTRAL")
        self.qqq_metrics['regime'] = regimes

        # 2. 개별 종목 데이터 다운로드 및 기술 지표 계산
        # 벌크 다운로드 활용하여 속도 극대화
        logger.info(f"[Backtest] Fetching target tickers data: {self.tickers}")
        bulk_data = await fetch_bulk_ohlcv(self.tickers, interval=self.interval, period=period_str)
        
        for ticker in self.tickers:
            try:
                if isinstance(bulk_data.columns, pd.MultiIndex):
                    if ticker not in bulk_data.columns.get_level_values(0):
                        logger.warning(f"[Backtest] Ticker {ticker} missing in download. Skipping.")
                        continue
                    df = bulk_data[ticker].dropna()
                else:
                    df = bulk_data.dropna()
                
                if df.empty or len(df) < 50:
                    logger.warning(f"[Backtest] Ticker {ticker} has too few data points ({len(df)}). Skipping.")
                    continue
                
                # 타임존 필터 정렬
                df = df[(df.index >= self.start_date) & (df.index <= self.end_date)]
                if df.empty:
                    continue
                
                self.tickers_data[ticker] = df
                
                # 지표 벡터화 연산
                metrics = pd.DataFrame(index=df.index)
                metrics['Open'] = df['Open']
                metrics['High'] = df['High']
                metrics['Low'] = df['Low']
                metrics['Close'] = df['Close']
                metrics['Volume'] = df['Volume']
                
                # 지표 추가
                metrics['EMA9'] = calculate_ema(df['Close'], 9)
                metrics['EMA20'] = calculate_ema(df['Close'], 20)
                metrics['EMA120'] = calculate_ema(df['Close'], 120)
                metrics['RSI'] = calculate_rsi(df['Close'], 14)
                
                macd_line, sig_line, _ = calculate_macd(df['Close'])
                metrics['MACD_line'] = macd_line
                metrics['MACD_signal'] = sig_line
                metrics['ATR'] = calculate_atr(df, 14)
                
                # VWAP 및 Wick 계산
                metrics['VWAP'] = calculate_vwap(df)
                metrics['Wick'] = calculate_wick_ratio(df)
                
                # RVOL (최근 20봉 평균 대비 현재 거래량)
                vol_ma = df['Volume'].rolling(window=20).mean()
                metrics['RVOL'] = df['Volume'] / vol_ma.shift(1)
                metrics['RVOL'] = metrics['RVOL'].fillna(1.0)
                
                # OBV 매집 판정
                metrics['OBV_divergence'] = calculate_obv_divergence(df)
                
                # RSI 볼린저밴드 하단 극점 판독 (RSI BB)
                rsi_vals, _, rsi_lower = calculate_rsi_bb(df)
                metrics['RSI_lower_bb'] = rsi_lower
                metrics['is_rsi_bb_extreme'] = rsi_vals < rsi_lower
                
                # 스마트 익절 감지용 시그널 (RSI 과매수 + MACD 데드크로스)
                macd_prev = metrics['MACD_line'].shift(1)
                sig_prev = metrics['MACD_signal'].shift(1)
                is_dead_cross = (metrics['MACD_line'] < metrics['MACD_signal']) & (macd_prev >= sig_prev)
                metrics['is_smart_exit'] = (metrics['RSI'] >= 70.0) & is_dead_cross
                
                # 52주 신고가 근접 비율
                high_52w = df['High'].cummax()
                metrics['dist_to_high'] = (df['Close'] / high_52w.shift(1) - 1) * 100
                metrics['is_near_52w_high'] = df['Close'] >= high_52w.shift(1) * 0.98

                # 3연속 거래량 실린 강세 양봉
                c_up = df['Close'] > df['Close'].shift(1)
                v_up = df['Volume'] > df['Volume'].shift(1)
                metrics['momentum_candles'] = (c_up & c_up.shift(1) & c_up.shift(2) & 
                                               v_up & v_up.shift(1) & v_up.shift(2))
                
                # 💡 [세계적인 유명 전략용 신규 지표 탑재]
                # 1. 래리 코너스(Larry Connors) RSI 2 및 EMA 5
                metrics['RSI2'] = calculate_rsi(df['Close'], 2)
                metrics['EMA5'] = calculate_ema(df['Close'], 5)
                
                # 2. 존 카터(John Carter) 볼린저 밴드 스퀴즈 (BB Squeeze)
                ma20 = df['Close'].rolling(window=20).mean()
                std20 = df['Close'].rolling(window=20).std()
                metrics['upper_bb'] = ma20 + 2 * std20
                metrics['lower_bb'] = ma20 - 2 * std20
                
                atr20 = calculate_atr(df, 20)
                metrics['upper_kc'] = ma20 + 1.5 * atr20
                metrics['lower_kc'] = ma20 - 1.5 * atr20
                
                is_squeeze = (metrics['upper_bb'] < metrics['upper_kc']) & (metrics['lower_bb'] > metrics['lower_kc'])
                metrics['was_squeeze'] = is_squeeze.rolling(window=5).max() > 0
                metrics['bb_breakout'] = df['Close'] > metrics['upper_bb']
                metrics['is_squeeze_breakout'] = metrics['was_squeeze'] & metrics['bb_breakout']
                
                # 💡 [전략 패턴] 지수 대비 강세 (Relative Strength) 사전 연산 및 저장
                if self.qqq_metrics is not None and not self.qqq_metrics.empty:
                    qqq_returns = self.qqq_metrics['Close'] / self.qqq_metrics['Close'].iloc[0] - 1
                    stock_returns = df['Close'] / df['Close'].iloc[0] - 1
                    metrics['relative_strength'] = stock_returns - qqq_returns
                    metrics['relative_strength'] = metrics['relative_strength'].fillna(0.0)
                else:
                    metrics['relative_strength'] = 0.0
                
                self.processed_metrics[ticker] = metrics
                
            except Exception as e:
                logger.exception(f"[Backtest] Failed to pre-calculate indicators for {ticker}: {e}")

        # 3. 공통 타임라인 결합 (QQQ와 타겟 종목들이 모두 겹치는 공통 거래 시간 추출)
        # 백테스팅은 QQQ 지수 타임스탬프 기준으로 흘러갑니다
        self.timeline = sorted(list(self.qqq_data.index))
        logger.info(f"[Backtest prepare_data] Complete. Timeline established: {len(self.timeline)} timestamps. Tickers: {list(self.tickers_data.keys())}")

    def _calculate_score(self, ticker: str, timestamp: datetime, regime: str, is_entry: bool = True) -> float:
        """가상 시점 t 기준, 개별 종목의 지표들을 장착된 전략 클래스를 통해 채점합니다."""
        metrics = self.processed_metrics[ticker]
        if timestamp not in metrics.index:
            return 0.0
            
        row = metrics.loc[timestamp]
        return self.strategy.calculate_score(row, regime, is_entry)

    def run(self):
        """정렬된 시간축을 순차적으로 흘려보내며 매수실패/체결/익절/손절 시나리오를 구동합니다."""
        logger.info("[Backtest] Simulation loop started.")
        
        for step, t in enumerate(self.timeline):
            qqq_row = self.qqq_metrics.loc[t]
            regime = qqq_row['regime']
            
            # 1. 현재 시점 t 기준 유효한 모든 티커들의 실시간 가격 사전 정리
            current_prices = {}
            for ticker in self.tickers_data:
                metrics = self.processed_metrics[ticker]
                if t in metrics.index:
                    current_prices[ticker] = float(metrics.loc[t, 'Close'])

            # 2. 포트폴리오 평가가치 기록 및 누적 그래프 업데이트
            self.broker.update_equity(t, current_prices)

            # 3. 보유 종목 모니터링 및 매도/탈출 판정 (Trailing Stop, Stop Loss, Smart Exit)
            holdings_to_check = list(self.broker.holdings.keys())
            for ticker in holdings_to_check:
                if ticker not in current_prices:
                    continue
                    
                h = self.broker.holdings[ticker]
                price = current_prices[ticker]
                metrics = self.processed_metrics[ticker]
                row = metrics.loc[t]
                
                # 보유 최고가(Peak) 갱신
                if price > h["highest_price"]:
                    h["highest_price"] = price

                profit_rate = ((price - h["avg_price"]) / h["avg_price"]) * 100
                score = self._calculate_score(ticker, t, regime, is_entry=False)
                
                # ATR 기반 동적 익절/손절선 가중 계산
                atr = row['ATR']
                
                # 💡 [전략 패턴] 동적 손절선 및 트레일링 스탑 비율 계산
                stop_loss_pct = self.strategy.get_stop_loss_pct(atr, price)
                trailing_stop_pct = self.strategy.get_trailing_stop_pct(atr, price)

                sell_reason = None
                is_breached = False
                breach_reason = ""

                # [지표 2] 동적 손절선 이탈
                if profit_rate <= -stop_loss_pct:
                    is_breached = True
                    breach_reason = f"동적 손절선 이탈 (손절선 -{stop_loss_pct:.2f}% 돌파 | 수익률: {profit_rate:.2f}%)"
                    
                # [지표 3] 동적 트레일링 스탑 이탈
                elif price <= h["highest_price"] * (1 - trailing_stop_pct / 100) and h["highest_price"] > h["avg_price"]:
                    is_breached = True
                    breach_reason = f"동적 트레일링 스탑 이탈 (최고가 대비 -{trailing_stop_pct:.2f}% 하락 | 수익률: {profit_rate:.2f}%)"

                # 💡 손절선/트레일링 스탑 이탈 감지 시, 연속 2회 확정식 가드 적용
                if is_breached:
                    self.breach_counts[ticker] = self.breach_counts.get(ticker, 0) + 1
                    count = self.breach_counts[ticker]
                    
                    if count >= 2:
                        sell_reason = breach_reason + " [2회 연속 이탈 확정]"
                else:
                    self.breach_counts.pop(ticker, None)

                # ⭐ [지표 1] 조기 스마트 익절 (RSI 다이버전스/MACD 크로스 조건)
                # 전략 A 등 스마트 익절이 없으면 min_smart_exit_profit이 999라 자연스럽게 통과
                if not sell_reason and profit_rate >= self.strategy.min_smart_exit_profit and row['is_smart_exit']:
                    sell_reason = f"스마트 조기 익절 (RSI-MACD 조건 충족 | 수익률: {profit_rate:.2f}%)"
                    
                # [지표 4] 기술적 강세 시그널 붕괴 - 시그널 붕괴는 버퍼 없이 바로 집행
                elif not sell_reason:
                    if self.strategy.is_signal_collapsed(score, regime):
                        sell_reason = f"강세 시그널 붕괴 ({score}점 도달)"

                if sell_reason:
                    # 매도 체결
                    self.broker.sell_order(ticker, h["quantity"], price, sell_reason, t)
                    self.breach_counts.pop(ticker, None)  # 매도 성공 시 캐시 비우기

            # 4. 신규 매수 기회 채점 및 1:2:6 피라미딩 자금 관리 집행
            cutoff_score = self.strategy.get_cutoff_score(regime)
            
            # 매 타임스탬프마다 컷오프 점수를 충족하는 종목 후보군 수집
            scored_candidates = []
            for ticker in self.tickers_data:
                if ticker not in current_prices:
                    continue
                score = self._calculate_score(ticker, t, regime, is_entry=True)
                if score >= cutoff_score:
                    scored_candidates.append((ticker, score))
            
            # 점수 높은 순 정렬
            scored_candidates = sorted(scored_candidates, key=lambda x: -x[1])
            
            for ticker, score in scored_candidates:
                price = current_prices[ticker]
                row = self.processed_metrics[ticker].loc[t]
                
                # ① 매도 후 20분(또는 20개 봉) 쿨다운 검사
                last_sell = self.broker.sell_cooldowns.get(ticker)
                if last_sell:
                    # 봉 단위 인터벌에 맞춰 쿨다운 검사 (1분봉 -> 20분 / 1시간봉 -> 2봉 등 유동적 분기)
                    cooldown_minutes = 20 if self.interval == "1m" else 120
                    time_diff = (t - last_sell).total_seconds() / 60.0
                    if time_diff < cooldown_minutes:
                        continue  # 쿨다운 활성 상태로 매수 생략

                existing_holding = self.broker.holdings.get(ticker)
                
                proposed_alloc_factor = 1.0
                next_stage = 3
                
                if existing_holding:
                    # 💡 기존 보유 중인 경우: 상승장(BULLISH) 모드에서만 피라미딩(불타기) 추가 매수 허용 (전략 A 등 피라미딩 미지원 시 pyramid_trigger_1=999로 자동 탈출)
                    pyramid_trigger_1 = self.strategy.get_pyramid_trigger(1)
                    if pyramid_trigger_1 > 100.0 or regime != "BULLISH":
                        continue
                        
                    buy_stage = existing_holding["buy_stage"]
                    profit_rate = ((price - existing_holding["avg_price"]) / existing_holding["avg_price"]) * 100
                    pyramid_trigger_2 = self.strategy.get_pyramid_trigger(2)

                    if buy_stage == 1:
                        if profit_rate >= pyramid_trigger_1:
                            proposed_alloc_factor = 0.35  # 2차 추가 매수 비중: 35%
                            next_stage = 2
                        else:
                            continue
                    elif buy_stage == 2:
                        if profit_rate >= pyramid_trigger_2:
                            proposed_alloc_factor = 0.50  # 3차 추가 매수 비중: 50%
                            next_stage = 3
                        else:
                            continue
                    else:
                        continue  # 이미 3단계 풀배팅 상태
                else:
                    # 💡 신규 포지션 진입 분기
                    proposed_alloc_factor = self.strategy.get_initial_entry_factor(regime)
                    if regime == "BULLISH" and proposed_alloc_factor < 1.0:
                        next_stage = 1  # 정찰병 15% 진입
                    else:
                        next_stage = 3  # 즉시 풀비중 진입

                # ② 포지션 크기 (Position Sizing) 수학 공식 적용
                base_alloc_usd = self.broker.portfolio_value * self.strategy.base_allocation_pct
                if self.strategy.min_allocation_usd > 0.0:
                    base_alloc_usd = max(self.strategy.min_allocation_usd, base_alloc_usd)
                
                # ATR 변동성 팩터
                atr = row['ATR']
                vol_factor = 1.0
                if atr > 0:
                    atr_pct = (atr / price) * 100
                    if atr_pct > 0:
                        vol_factor = max(0.5, min(1.5, 2.0 / atr_pct))
                
                # 시그널 스코어 가중치 배수
                score_factor = 1.0 + (score - cutoff_score) * 0.05
                
                proposed_value = base_alloc_usd * vol_factor * score_factor * proposed_alloc_factor
                proposed_qty = proposed_value / price
                
                # 예수금 안전장치
                max_order_budget = self.broker.cash * 0.95
                final_qty = int(min(proposed_qty, max_order_budget / price))
                
                if final_qty >= 1:
                    # 매수 집행
                    self.broker.buy_order(ticker, final_qty, price, next_stage, t)

        logger.info("[Backtest] Simulation loop complete.")
        return self.get_summary_report()

    def get_summary_report(self) -> dict:
        """백테스팅 결과를 집계하여 퀀트 성적표 요약 딕셔너리를 반환합니다."""
        df_eq = pd.DataFrame(self.broker.equity_curve)
        if df_eq.empty:
            return {"error": "No equity data collected during backtest."}
            
        initial_val = self.broker.initial_cash
        final_val = df_eq['total'].iloc[-1]
        total_pnl = final_val - initial_val
        total_return_pct = (total_pnl / initial_val) * 100
        
        # MDD(최대 낙폭) 계산 공식
        df_eq['peak'] = df_eq['total'].cummax()
        df_eq['drawdown'] = (df_eq['total'] - df_eq['peak']) / df_eq['peak']
        mdd_pct = df_eq['drawdown'].min() * 100
        
        # 거래 통계 집계
        sells = [log for log in self.broker.trade_logs if log['trade_type'] == "SELL"]
        total_trades = len(sells)
        
        winning_trades = len([log for log in sells if log['realized_pnl'] > 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        total_profit = sum(log['realized_pnl'] for log in sells if log['realized_pnl'] > 0)
        total_loss = abs(sum(log['realized_pnl'] for log in sells if log['realized_pnl'] < 0))
        
        profit_factor = (total_profit / total_loss) if total_loss > 0 else (999.9 if total_profit > 0 else 0.0)

        # QQQ 지수 자체의 동일 기간 보유 수익률(Buy & Hold) 대조용 계산
        qqq_initial = self.qqq_metrics['Close'].iloc[0]
        qqq_final = self.qqq_metrics['Close'].iloc[-1]
        qqq_return_pct = ((qqq_final - qqq_initial) / qqq_initial) * 100

        return {
            "initial_cash": round(initial_val, 2),
            "final_value": round(final_val, 2),
            "total_pnl": round(total_pnl, 2),
            "total_return_rate": round(total_return_pct, 2),
            "mdd": round(mdd_pct, 2),
            "total_trades": total_trades,
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "qqq_bench_return_rate": round(qqq_return_pct, 2),
            "trade_logs": self.broker.trade_logs,
            "equity_curve": self.broker.equity_curve
        }
