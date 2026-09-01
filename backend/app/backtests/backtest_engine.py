import pandas as pd
import numpy as np
import asyncio
from datetime import datetime, timedelta
from app.scanner.data_provider import fetch_ohlcv, fetch_bulk_ohlcv
from app.scanner.indicators import (
    calculate_ema, calculate_rsi, calculate_macd, calculate_atr, 
    calculate_obv_divergence, calculate_rsi_bb, calculate_vwap, calculate_wick_ratio,
    calculate_double_bb_reversion_signals, calculate_connors_rsi
)
from app.core.logging import logger
from app.backtests.backtest_metrics import calculate_performance_metrics
from app.scanner.indicator_metrics import (
    build_indicator_metrics,
    build_qqq_regime_metrics,
)
from app.scanner.macro_data import fetch_macro_series
from app.bot.trade_calculations import (
    DEFAULT_ROLLING_BOX_MINUTES,
    bar_minutes_for_interval,
    resolve_rolling_box_bars,
    calculate_buy_total,
    calculate_realized_pnl,
    check_rolling_box_breach,
    compute_rolling_box_stop,
)

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
        fee_rate = settings.SIMULATED_FEE_RATE
        _, _, total_cost = calculate_buy_total(price, quantity, fee_rate)
        # calculate_buy_total은 Decimal을 반환하지만 백테스트 브로커 잔고(self.cash)는 float 기반이므로
        # 경계에서 float로 코어싱해 float↔Decimal 혼합 연산 크래시(TypeError)를 방지한다.
        total_cost = float(total_cost)

        if self.cash < total_cost:
            # 잔고 안전장치: 남은 예수금 내에서 수수료까지 감안하여 최대한 매매 시도
            max_qty = int(self.cash / (price * (1 + float(fee_rate))))
            if max_qty >= 1:
                quantity = max_qty
                _, _, total_cost = calculate_buy_total(price, quantity, fee_rate)
                total_cost = float(total_cost)
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
                "ticker_name": ticker_name or h["ticker_name"],
                "rolling_stop": h.get("rolling_stop", 0.0)  # 불타기 시 기존 래칫 스탑 유지
            }
        else:
            # 💡 신규 포지션 진입
            self.holdings[ticker] = {
                "quantity": quantity,
                "avg_price": price,
                "highest_price": price,
                "buy_stage": buy_stage,
                "ticker_name": ticker_name or ticker,
                "rolling_stop": 0.0  # 롤링 박스 스탑 래칫 초기값 (첫 모니터링 봉에서 시드)
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
        pnl = calculate_realized_pnl(
            avg_price=h["avg_price"],
            filled_price=price,
            quantity=sell_qty,
            fee_rate=settings.SIMULATED_FEE_RATE,
        )
        # RealizedPnL 필드는 Decimal이지만 백테스트 잔고/로그는 float 기반이므로 경계에서 코어싱한다.
        self.cash += float(pnl.net_revenue)

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
            "realized_pnl": round(float(pnl.realized_pnl), 2),
            "return_rate": round(float(pnl.return_rate), 2),
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
    def __init__(self, tickers: list, start_date: str, end_date: str, interval: str = "1h", initial_cash: float = 10000.0, csv_path: str = None, strategy_type: str = "complex", variant: str = "BASE", download_only: bool = False):
        self.tickers = sorted(list(set(tickers)))
        self.start_date = start_date
        self.end_date = end_date
        self.interval = interval
        self.csv_path = csv_path
        self.broker = BacktestBroker(initial_cash)
        self.strategy_type = strategy_type
        self.download_only = download_only
        
        # 💡 [전략 패턴] 전략 팩토리를 통해 해당 전략 객체 로드 및 장착
        from app.strategies.strategy_factory import get_strategy
        self.strategy = get_strategy(strategy_type)
        
        # 💡 6대 변형 시나리오 제어 변수 설정
        self.variant = variant.upper().strip()
        
        # 1) 이탈 확정 횟수 (exit_confirm_count): 기본값 2, BUF3/WHIP/FULL 일 때 3
        if self.variant in ["BUF3", "WHIP", "FULL"]:
            self.exit_confirm_count = 3
        else:
            self.exit_confirm_count = 2
            
        # 2) 당일 재진입 금지 (day_lock_enabled): LOCK/WHIP/FULL 일 때 True
        if self.variant in ["LOCK", "WHIP", "FULL"]:
            self.day_lock_enabled = True
        else:
            self.day_lock_enabled = False
            
        # 3) 상승장 100% 비중 강제 (bullish_alloc_100): P100/FULL 일 때 True
        if self.variant in ["P100", "FULL"]:
            self.bullish_alloc_100 = True
        else:
            self.bullish_alloc_100 = False
            
        # 💡 이탈 연속 횟수 추적 캐시
        self.breach_counts = {}  # {ticker: count}
        
        # 다운로드된 원시 데이터들 저장소
        self.tickers_data = {}  # {ticker: DataFrame}
        self.qqq_data = None  # QQQ DataFrame
        
        # 미리 계산된 지표 시계열 데이터 저장소 (시뮬레이션 가속화용)
        self.processed_metrics = {}  # {ticker: DataFrame}
        self.qqq_metrics = None  # DataFrame containing QQQ indicators
        self.timeline = []  # 정렬된 공통 시계열 타임스탬프 리스트

    @staticmethod
    def _slice_requested_range(
        frame: pd.DataFrame,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        if frame.empty:
            return frame

        start = pd.Timestamp(start_date)
        end_exclusive = pd.Timestamp(end_date) + pd.Timedelta(days=1)
        if frame.index.tz is not None:
            start = start.tz_localize(frame.index.tz)
            end_exclusive = end_exclusive.tz_localize(frame.index.tz)
        return frame[(frame.index >= start) & (frame.index < end_exclusive)]

    async def prepare_data(self):
        """QQQ 및 대상 티커들의 데이터를 다운로드하고 모든 기술적 지표를 벡터화 사전 연산하여 타임라인을 구축합니다."""
        logger.info(f"[Backtest prepare_data] Sourcing data from {self.start_date} to {self.end_date} (Interval: {self.interval})")
        
        # 1. QQQ 지수 데이터 수집 (레짐 스위칭용)
        # 1시간봉/일봉 백테스트 시에는 동일 인터벌을 적용하고, 1분봉 정밀 시에는 1분봉 QQQ 데이터와 15분봉 QQQ 데이터를 적절히 조화시킵니다.
        # 여기서는 주 인터벌 데이터를 기준으로 정합합니다.
        start_datetime = datetime.strptime(self.start_date, "%Y-%m-%d")
        end_datetime = datetime.strptime(self.end_date, "%Y-%m-%d")
        period_diff = (end_datetime - start_datetime).days
        if period_diff < 0:
            raise ValueError("Backtest start_date must be earlier than end_date.")
        period_str = f"{period_diff + 5}d"  # 주말 마진 추가
        warmup_days = {
            "1m": 5,
            "15m": 15,
            "1h": 45,
            "1d": 240,
        }.get(self.interval, 60)
        # 자율 슬롯(레짐 상태기계)은 신호 지수의 장기 SMA(예: 200일)를 요구하므로, 요청 시작일에서
        # SMA가 유효하려면 그 이전에 최소 sma_period 거래일이 다운로드돼야 한다. 거래일↔달력일
        # 환산(~1.5배) + 여유를 두어 워밍업을 확대한다(스캐너 경로 무영향, 다운로드 범위만 확장).
        if getattr(self.strategy, "is_autonomous", False):
            sma_period = int(getattr(self.strategy, "sma_period", 200))
            warmup_days = max(warmup_days, int(sma_period * 1.6) + 30)
        download_start = start_datetime - timedelta(days=warmup_days)
        download_end = end_datetime + timedelta(days=1)
        
        # 💡 [yfinance API 한도 보호] 15m/5m/1m 데이터는 yfinance 보관 주기 한도(15m/5m 최대 60일, 1m 최대 30일)를 넘으면 
        # 다운로드가 통째로 실패하므로 download_start를 제공 한도 범위 안으로 안전하게 클리핑합니다.
        # yfinance 한도는 언제나 '현재 호출하는 시점(오늘)' 기준이므로, download_end가 아닌 datetime.now() 기준으로 역산하고 2일 안전 마진을 둡니다.
        limit_days = {
            "1m": 27,
            "5m": 57,
            "15m": 57,
        }.get(self.interval, None)
        
        if limit_days is not None:
            max_allowed_start = datetime.now() - timedelta(days=limit_days)
            if download_start < max_allowed_start:
                logger.warning(f"[Backtest] Interval {self.interval} requested start date {download_start.date()} exceeds yfinance limit. Clipping to {max_allowed_start.date()}")
                download_start = max_allowed_start
        
        # 1분봉은 최대 30일 제한이 있으므로 안전하게 period를 제한
        if self.interval == "1m":
            period_str = "30d"
            logger.warning("[Backtest] Interval 1m selected. Restricting range to maximum 30 days due to yfinance limit.")

        logger.info(f"[Backtest] Fetching QQQ index data...")
        self.qqq_data = await fetch_ohlcv(
            "QQQ",
            interval=self.interval,
            period=period_str,
            start=download_start,
            end=download_end,
        )
        if self.qqq_data.empty:
            raise Exception("Failed to fetch QQQ index data. Backtesting cannot proceed without regime guide.")

        # QQQ 지표·레짐 계산. 계산식의 단일 지점은 indicator_metrics다 -
        # 라이브 신호(signal_contract.daily_indicator_snapshot)도 같은 함수를 쓴다.
        qqq_metrics = build_qqq_regime_metrics(self.qqq_data)

        # 매크로 시계열(FRED)은 종목과 무관한 공통 값이라 한 번만 받는다.
        # 수집 실패 시 None이며, 그러면 매크로 열이 만들어지지 않아 해당 전략은
        # 진입하지 않는다(틀린 값으로 매매하는 것보다 안전하다).
        self.macro_data = fetch_macro_series()
        self.qqq_metrics = self._slice_requested_range(
            qqq_metrics,
            self.start_date,
            self.end_date,
        )
        if self.qqq_metrics.empty:
            raise Exception(
                "QQQ data does not cover the requested backtest date range."
            )

        # 벌크 다운로드 활용하여 속도 극대화 (50개씩 청킹하여 다운로드 후 병합)
        logger.info(f"[Backtest] Fetching target tickers data (chunked bulk): {self.tickers}")
        chunk_size = 50
        ticker_chunks = [self.tickers[i:i+chunk_size] for i in range(0, len(self.tickers), chunk_size)]
        
        bulk_dfs = []
        for chunk in ticker_chunks:
            chunk_data = await fetch_bulk_ohlcv(
                chunk,
                interval=self.interval,
                period=period_str,
                start=download_start,
                end=download_end,
            )
            if not chunk_data.empty:
                bulk_dfs.append(chunk_data)
            await asyncio.sleep(0.3)  # API 가드용 지연
            
        if bulk_dfs:
            bulk_data = pd.concat(bulk_dfs, axis=1)
        else:
            bulk_data = pd.DataFrame()

        if self.download_only:
            logger.info("[Backtest] download_only is True. Skipping indicators calculation.")
            self.tickers_data = {}
            for ticker in self.tickers:
                if isinstance(bulk_data.columns, pd.MultiIndex):
                    if ticker in bulk_data.columns.get_level_values(0):
                        self.tickers_data[ticker] = bulk_data[ticker].dropna()
                else:
                    self.tickers_data[ticker] = bulk_data.dropna()
            return
        
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
                
                requested_df = self._slice_requested_range(
                    df,
                    self.start_date,
                    self.end_date,
                )
                if requested_df.empty:
                    continue
                
                # 지표 벡터화 연산
                metrics = build_indicator_metrics(
                    df,
                    qqq_data=self.qqq_data,
                    qqq_metrics=self.qqq_metrics,
                    macro_data=getattr(self, 'macro_data', None),
                    interval=self.interval,
                    rolling_box_minutes=getattr(
                        self.strategy, 'rolling_box_minutes', DEFAULT_ROLLING_BOX_MINUTES
                    ),
                )
                
                self.tickers_data[ticker] = requested_df
                self.processed_metrics[ticker] = metrics
                
            except Exception as e:
                logger.exception(f"[Backtest] Failed to pre-calculate indicators for {ticker}: {e}")

        # 3. 공통 타임라인 결합 (QQQ와 타겟 종목들이 모두 겹치는 공통 거래 시간 추출)
        # 백테스팅은 QQQ 지수 타임스탬프 기준으로 흘러갑니다
        self.timeline = sorted(list(self.qqq_metrics.index))
        logger.info(f"[Backtest prepare_data] Complete. Timeline established: {len(self.timeline)} timestamps. Tickers: {list(self.tickers_data.keys())}")

    def _calculate_score(self, ticker: str, timestamp: datetime, regime: str, is_entry: bool = True) -> float:
        """가상 시점 t 기준, 개별 종목의 지표들을 장착된 전략 클래스를 통해 채점합니다."""
        metrics = self.processed_metrics[ticker]
        if timestamp not in metrics.index:
            return 0.0
            
        row = metrics.loc[timestamp]
        return self.strategy.calculate_score(row, regime, is_entry)

    def _run_autonomous(self):
        """자율 슬롯(지수 레버리지 레짐 계열) 전용 백테스트 경로.

        스캐너 채점(calculate_score)·손절/트레일링/피라미딩을 일절 사용하지 않는다. 대신
        신호 지수(QQQ) 완결 일봉으로 LeveragedRegime.compute_state_series(상태기계 SSOT)를 한 번
        계산하고, 매 봉에서 '직전 완결봉의 확정 상태'로 판정해 자산 티커(QLD/TQQQ/QQQ)를 전액
        매수(IN)하거나 전량 청산(OUT)한다. 판정은 close[t]에서 나오고 체결은 t+1 봉가로 이뤄지므로
        룩어헤드가 없다(라이브 process_autonomous_slots와 등가).
        """
        if self.interval != "1d":
            raise ValueError(
                f"자율 슬롯 전략은 일봉(1d) 백테스트만 지원합니다(요청 인터벌: {self.interval}). "
                "레짐 상태기계가 일별 SMA/확정일 기준으로 정의됩니다."
            )

        asset = getattr(self.strategy, "asset_ticker", None)
        if asset not in self.processed_metrics:
            raise ValueError(
                f"자율 슬롯 자산 티커 '{asset}'의 데이터가 준비되지 않았습니다. "
                f"백테스트 유니버스(tickers)에 '{asset}'를 포함해야 합니다."
            )

        # 상태 시계열은 워밍업을 포함한 '전체' 일봉으로 계산해야 요청 시작일에서 SMA가 유효하다.
        state_series = self.strategy.compute_state_series(self.qqq_data["Close"])
        asset_metrics = self.processed_metrics[asset]

        logger.info(
            f"[Backtest][Autonomous] {self.strategy.name} | 자산={asset} | "
            f"타임라인 {len(self.timeline)}봉 | 신호=QQQ SMA{getattr(self.strategy, 'sma_period', '?')}"
        )

        # 직전 완결봉의 확정 상태(룩어헤드 차단). 시작 전 기본은 현금(OUT).
        prev_state = "OUT"
        for t in self.timeline:
            if t not in asset_metrics.index:
                # 자산 상장 이전 구간 등 가격 부재 봉은 현금 보유로 평가(스킵).
                continue
            price = float(asset_metrics.loc[t, "Close"])

            # 1. 마크투마켓 (자산 1종만 평가)
            self.broker.update_equity(t, {asset: price})

            # 2. 직전 완결봉 상태로 목표 집행 (체결은 현재 봉가 = 신호 익일 체결 등가)
            holding = self.broker.holdings.get(asset)
            if prev_state == "IN" and holding is None:
                fee = float(settings.SIMULATED_FEE_RATE)
                qty = int(self.broker.cash / (price * (1 + fee))) if price > 0 else 0
                if qty >= 1:
                    self.broker.buy_order(asset, qty, price, buy_stage=3, timestamp=t, ticker_name=asset)
            elif prev_state == "OUT" and holding is not None:
                self.broker.sell_order(
                    asset, holding["quantity"], price, "레짐 이탈(OUT) 전량 청산", t
                )

            # 3. 현재 봉의 확정 상태를 다음 루프의 '직전 상태'로 넘긴다.
            state_at_t = state_series.get(t)
            if state_at_t is not None:
                prev_state = str(state_at_t)

        logger.info("[Backtest][Autonomous] Simulation loop complete.")
        return self.get_summary_report()

    def run(self):
        """정렬된 시간축을 순차적으로 흘려보내며 매수실패/체결/익절/손절 시나리오를 구동합니다."""
        # 자율 슬롯 전략(레버리지 레짐 계열)은 종목 채점 파이프라인을 쓰지 않으므로 전용 경로로 분기한다.
        # 스캐너 경로(아래 로직)는 무변경으로 완전히 격리 보존된다.
        if getattr(self.strategy, "is_autonomous", False):
            return self._run_autonomous()

        logger.info("[Backtest] Simulation loop started.")

        # 정합성 가드: 다운로드 실패 등으로 tickers_data와 processed_metrics가 어긋나면
        # 아래 루프의 self.processed_metrics[ticker] 접근이 KeyError로 백테스트 전체를 죽인다.
        # 지표가 계산된(processed_metrics에 있는) 티커만 남겨 불일치를 사전 차단한다.
        missing = [tk for tk in list(self.tickers_data) if tk not in self.processed_metrics]
        if missing:
            logger.warning(
                f"[Backtest] processed_metrics에 없는 {len(missing)}개 티커를 정합성 가드로 제외합니다: {missing}"
            )
            for tk in missing:
                self.tickers_data.pop(tk, None)

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

                # [지표 2-보조] 롤링 박스 스탑 래칫 갱신 (opt-in 전략 한정, 판정 전에 항상 갱신)
                use_rolling_box = bool(getattr(self.strategy, 'use_rolling_box_stop', False))
                if use_rolling_box:
                    window_low = row.get('rolling_box_low')
                    if window_low is not None and pd.notna(window_low):
                        h["rolling_stop"] = float(compute_rolling_box_stop(h.get("rolling_stop", 0.0), window_low))

                # [지표 2] 동적 손절선 이탈
                if profit_rate <= -stop_loss_pct:
                    is_breached = True
                    breach_reason = f"동적 손절선 이탈 (손절선 -{stop_loss_pct:.2f}% 돌파 | 수익률: {profit_rate:.2f}%)"

                # [지표 3] 동적 트레일링 스탑 이탈
                elif price <= h["highest_price"] * (1 - trailing_stop_pct / 100) and h["highest_price"] > h["avg_price"]:
                    is_breached = True
                    breach_reason = f"동적 트레일링 스탑 이탈 (최고가 대비 -{trailing_stop_pct:.2f}% 하락 | 수익률: {profit_rate:.2f}%)"

                # [지표 3-보조] 롤링 박스 스탑 이탈 (최근 N봉 저점 박스 하단 래칫 이탈)
                elif use_rolling_box and check_rolling_box_breach(price, h.get("rolling_stop", 0.0), h["highest_price"], h["avg_price"]):
                    is_breached = True
                    breach_reason = f"롤링 박스 스탑 이탈 (박스 하단 ${h['rolling_stop']:.2f} 붕괴 | 수익률: {profit_rate:.2f}%)"

                # 💡 손절선/트레일링 스탑 이탈 감지 시, 연속 N회 확정식 가드 적용
                if is_breached:
                    self.breach_counts[ticker] = self.breach_counts.get(ticker, 0) + 1
                    count = self.breach_counts[ticker]
                    
                    if count >= self.exit_confirm_count:
                        sell_reason = breach_reason + f" [{self.exit_confirm_count}회 연속 이탈 확정]"
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
                
                # ① 매도 후 20분(또는 20개 봉) 쿨다운 및 당일 재진입 락 검사
                last_sell = self.broker.sell_cooldowns.get(ticker)
                if last_sell:
                    # 당일 재진입 금지 락(Day Lock) 검사
                    if self.day_lock_enabled and t.date() == last_sell.date():
                        continue  # 동일 날짜에 매도 이력이 있으면 진입 생략
                        
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
                    if self.bullish_alloc_100 and regime == "BULLISH":
                        proposed_alloc_factor = 1.0
                        
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
        performance_metrics = calculate_performance_metrics(
            self.broker.equity_curve,
            initial_value=initial_val,
        )

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
            **performance_metrics,
            "trade_logs": self.broker.trade_logs,
            "equity_curve": self.broker.equity_curve
        }
