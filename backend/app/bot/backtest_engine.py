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
    def __init__(self, tickers: list, start_date: str, end_date: str, interval: str = "1h", initial_cash: float = 10000.0, csv_path: str = None):
        self.tickers = list(set(tickers))
        self.start_date = start_date
        self.end_date = end_date
        self.interval = interval
        self.csv_path = csv_path
        self.broker = BacktestBroker(initial_cash)
        
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
                
                self.processed_metrics[ticker] = metrics
                
            except Exception as e:
                logger.exception(f"[Backtest] Failed to pre-calculate indicators for {ticker}: {e}")

        # 3. 공통 타임라인 결합 (QQQ와 타겟 종목들이 모두 겹치는 공통 거래 시간 추출)
        # 백테스팅은 QQQ 지수 타임스탬프 기준으로 흘러갑니다
        self.timeline = sorted(list(self.qqq_data.index))
        logger.info(f"[Backtest prepare_data] Complete. Timeline established: {len(self.timeline)} timestamps. Tickers: {list(self.tickers_data.keys())}")

    def _calculate_score(self, ticker: str, timestamp: datetime, regime: str) -> float:
        """가상 시점 t 기준, 개별 종목의 지표들을 2-Stage scorecard 공식에 따라 실시간 채점합니다."""
        metrics = self.processed_metrics[ticker]
        if timestamp not in metrics.index:
            return 0.0
            
        row = metrics.loc[timestamp]
        
        # 1. 필수 관문 필터 (단 하나라도 충족되지 않으면 즉시 0점 탈락)
        # 필수 거래대금 필터: 당일 거래대금 $1,000,000 이상 (여기서는 백테스트 데이터의 유효성 보장을 위해 volume * close 검증)
        dollar_volume = row['Close'] * row['Volume']
        if dollar_volume < 100000.0:  # 백테스트 종목 필터 완화 (유동성 부족에 따른 백테스트 먹통 방지)
            return 0.0
            
        # 세력선 지지 필터: 주가가 VWAP 위인지 확인 (VWAP 계산이 nan인 경우 통과시킴)
        if not pd.isna(row['VWAP']) and row['Close'] < row['VWAP']:
            return 0.0
            
        # 수급 활성 필터: 상대 거래량(RVOL) >= 1.2
        if row['RVOL'] < 1.1:  # 백테스트 감도 고려하여 미세 조정 (RVOL 필터 기본 1.1 완화)
            return 0.0

        score = 0
        
        # 💡 [Stage 1] 가점 요인 산출
        # RVOL 가점
        if row['RVOL'] >= 2.0: score += 30
        elif row['RVOL'] >= 1.2: score += 15
        
        # 신고가 저항 돌파 가점
        if not pd.isna(row['dist_to_high']) and row['dist_to_high'] > -1.5: score += 20
        # 지수 대비 강세 (Relative Strength)
        qqq_row = self.qqq_metrics.loc[timestamp]
        qqq_return = (qqq_row['Close'] / self.qqq_metrics['Close'].iloc[0] - 1)
        stock_return = (row['Close'] / metrics['Close'].iloc[0] - 1)
        if stock_return > qqq_return: score += 10
        
        # EMA 이평선 정배열 정방향 가점
        if row['EMA9'] > row['EMA20']: score += 10
        # 52주 역사적 신고가 인접 가점
        if row['is_near_52w_high']: score += 25
        # 3연속 모멘텀 양봉 가점
        if row['momentum_candles']: score += 15

        # 💡 [Stage 2] 장세 레짐 보너스/페널티 분기 채점
        if regime == "BULLISH":
            score += 5  # 상승장 보너스
            
            # VWAP 상방 가산점
            if not pd.isna(row['VWAP']) and row['Close'] > row['VWAP']: score += 10
            
            # 윗꼬리 매물 저항 없음 가점 (wick_ratio < 0.3)
            if row['Wick'] < 0.3: score += 10
            elif row['Wick'] > 0.5: score -= 20  # 윗꼬리 저항 패널티
            
        else:
            # BEARISH / NEUTRAL 장세
            # OBV 매집 골든크로스 가점 (divergence score 0~100점 기반 가중)
            if row['OBV_divergence'] > 0: score += 30
            else: score -= 20
            
            # 장기 일봉 120선 상방 안착 가점
            if row['Close'] > row['EMA120']: score += 30
            
            # RSI 볼밴 하단 극점 과매도 반발 가점
            if row['is_rsi_bb_extreme']: score += 30
            
            # 하락장 레짐 패널티
            if regime == "BEARISH": score -= 30
            
            if row['Wick'] < 0.3: score += 10
            elif row['Wick'] > 0.5: score -= 20

        return max(0, min(score, 100))

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

            # 3. 보유 포종목 모니터링 및 매도/탈출 판정 (Trailing Stop, Stop Loss, Smart Exit)
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
                score = self._calculate_score(ticker, t, regime)
                
                # ATR 기반 동적 익절/손절선 가중 계산
                atr = row['ATR']
                stop_loss_pct = 3.0  # 기본 최소 손절선 3.0%
                trailing_stop_pct = 2.0  # 기본 최소 트레일링 2.0%
                if atr > 0:
                    atr_pct = (atr / price) * 100
                    stop_loss_pct = max(3.0, atr_pct * 1.5)
                    trailing_stop_pct = max(2.0, atr_pct * 1.0)

                sell_reason = None

                # ⭐ [지표 1] 조기 스마트 익절 (RSI 다이버전스/MACD 크로스 조건)
                if profit_rate >= 1.0 and row['is_smart_exit']:
                    sell_reason = f"스마트 조기 익절 (RSI-MACD 조건 충족 | 수익률: {profit_rate:.2f}%)"
                    
                # [지표 2] 동적 손절선 이탈
                elif profit_rate <= -stop_loss_pct:
                    sell_reason = f"동적 손절선 이탈 (손절선 -{stop_loss_pct:.2f}% 돌파 | 수익률: {profit_rate:.2f}%)"
                    
                # [지표 3] 동적 트레일링 스탑 이탈
                elif price <= h["highest_price"] * (1 - trailing_stop_pct / 100) and h["highest_price"] > h["avg_price"]:
                    sell_reason = f"동적 트레일링 스탑 이탈 (최고가 대비 -{trailing_stop_pct:.2f}% 하락 | 수익률: {profit_rate:.2f}%)"
                    
                # [지표 4] 기술적 강세 시그널 붕괴
                elif (regime == "BULLISH" and score < 40) or (regime != "BULLISH" and score < 50):
                    sell_reason = f"강세 시그널 붕괴 ({score}점 도달)"

                if sell_reason:
                    # 매도 체결
                    self.broker.sell_order(ticker, h["quantity"], price, sell_reason, t)

            # 4. 신규 매수 기회 채점 및 1:2:6 피라미딩 자금 관리 집행
            # 상승장 컷오프 80점, 하락/횡보장 컷오프 90점
            cutoff_score = 80 if regime == "BULLISH" else 90
            
            # 매 타임스탬프마다 컷오프 점수를 충족하는 종목 후보군 수집
            scored_candidates = []
            for ticker in self.tickers_data:
                if ticker not in current_prices:
                    continue
                score = self._calculate_score(ticker, t, regime)
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
                    # 💡 기존 보유 중인 경우: 상승장(BULLISH) 모드에서만 피라미딩(불타기) 추가 매수 허용
                    if regime != "BULLISH":
                        continue
                        
                    buy_stage = existing_holding["buy_stage"]
                    profit_rate = ((price - existing_holding["avg_price"]) / existing_holding["avg_price"]) * 100
                    
                    if buy_stage == 1:
                        # 1단계 -> 2단계 피라미딩 조건: 평단 대비 +1.5% 이상 수익권
                        if profit_rate >= 1.5:
                            proposed_alloc_factor = 0.35  # 2차 추가 매수 비중: 35%
                            next_stage = 2
                        else:
                            continue
                    elif buy_stage == 2:
                        # 2단계 -> 3단계 피라미딩 조건: 평단 대비 +3.0% 이상 수익권
                        if profit_rate >= 3.0:
                            proposed_alloc_factor = 0.50  # 3차 추가 매수 비중: 50%
                            next_stage = 3
                        else:
                            continue
                    else:
                        continue  # 이미 3단계 풀배팅 상태
                else:
                    # 💡 신규 포지션 진입 분기
                    if regime == "BULLISH":
                        proposed_alloc_factor = 0.15  # 정찰병 15% 진입
                        next_stage = 1
                    else:
                        next_stage = 3  # 추가 불타기 불허 격리
                        if regime == "BEARISH":
                            proposed_alloc_factor = 0.30  # 하락장 비중 30% 제한
                        else:
                            proposed_alloc_factor = 0.50  # 횡보장 비중 50% 제한

                # ② 포지션 크기 (Position Sizing) 수학 공식 적용
                # 총자산의 10%를 기본 유닛으로 설정 (최소 $500 보장)
                base_alloc_usd = max(500.0, self.broker.portfolio_value * 0.10)
                
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
